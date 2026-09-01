"""Object storage services — presigned URL generation for Cloudflare R2.

Why presigned URLs rather than proxying uploads through Django: a photo upload
through the app server occupies a gunicorn worker for the whole transfer, on a
mobile connection that may take many seconds. Two users uploading at once would
consume both workers and the health check would start failing. Presigning moves
the bytes directly between the client and R2; the app server only ever handles
a small JSON request and never sees the image at all.

Everything here validates *before* signing. A signature is an authorisation, so
anything not checked at this point is not checked at all — R2 will honour
whatever the URL says it may do.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from django.conf import settings
from rest_framework.exceptions import ValidationError

# Uploads land under `pending/` and are promoted to `entries/` once something
# actually references them.
#
# This two-prefix split exists because R2 lifecycle rules match on prefix and
# age and nothing else — they cannot know whether a row in Postgres points at an
# object. A rule expiring `entries/` after N days would therefore delete every
# user's photos on their Nth day, which is data loss on a timer rather than
# orphan cleanup. Everything under `pending/` is by definition unclaimed, so
# expiring *that* prefix is always correct.
#
# The orphan this handles: a client presigns, uploads, then crashes before
# saving the entry. Without cleanup those objects accumulate forever, silently,
# on the bill.
#
# Retained `analyses/` objects do not have a lifecycle rule or cleanup owner yet.
# Failed or abandoned analyses remain there until a reconciliation job is added.
PENDING_PREFIX = "pending/"
ANALYSES_PREFIX = "analyses/"
ENTRIES_PREFIX = "entries/"


@dataclass(frozen=True)
class PresignedUpload:
    """A signed PUT authorisation plus the key the object will live at.

    The key is returned because the client has to hand it back when it saves the
    entry that references the object — it is the only durable identifier. The
    URL is single-use in practice and expires; the key does not.
    """

    url: str
    key: str
    expires_in: int
    max_bytes: int


def _client() -> Any:
    """Build an S3 client pointed at R2.

    Not cached at module scope: the settings it reads are patched in tests, and
    a module-level client would freeze whatever the first import happened to
    see. Client construction opens no connection, so this is cheap.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        # R2 has no regions but the SDK requires one; "auto" is what Cloudflare
        # specifies. An AWS region name signs fine and then fails at request
        # time, which is a confusing way to learn this.
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def build_object_key(user_id: int, content_type: str) -> str:
    """Key a freshly presigned upload: `pending/{user_id}/{uuid}.ext`.

    Uploads start under `pending/` because nothing references them yet — see the
    prefix constants above for why the lifecycle rule depends on that.

    The user_id segment is what makes account deletion tractable: enumerate and
    purge by prefix, rather than tracking every object individually in the
    database and hoping the two never diverge.

    The filename is a UUID rather than anything client-supplied. Client
    filenames invite collisions between users, path traversal via `../`, and
    leaking whatever the photo was called on someone's phone.
    """
    extension = settings.R2_ALLOWED_UPLOAD_TYPES[content_type]
    return f"{PENDING_PREFIX}{user_id}/{uuid.uuid4()}.{extension}"


def presign_upload(*, user_id: int, content_type: str, content_length: int) -> PresignedUpload:
    """Authorise one upload of exactly this type and size, to a key we choose.

    Both constraints are signed into the URL, not merely checked here. That
    distinction matters: a check that only happens in this function constrains
    the polite client that asked, while a signed constraint constrains whoever
    ends up holding the URL. R2 rejects a PUT whose Content-Type or
    Content-Length differs from what was signed.

    Raises ValidationError (a 400) rather than returning an error shape, so the
    caller stays a thin view.
    """
    if content_type not in settings.R2_ALLOWED_UPLOAD_TYPES:
        allowed = ", ".join(sorted(settings.R2_ALLOWED_UPLOAD_TYPES))
        raise ValidationError({"content_type": [f"Unsupported type. Allowed: {allowed}."]})

    if content_length > settings.R2_MAX_UPLOAD_BYTES:
        raise ValidationError(
            {
                "content_length": [
                    f"Exceeds the {settings.R2_MAX_UPLOAD_BYTES} byte limit.",
                ]
            }
        )

    key = build_object_key(user_id=user_id, content_type=content_type)
    expires_in = settings.R2_UPLOAD_URL_EXPIRY_SECONDS

    url = _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.R2_BUCKET_NAME,
            "Key": key,
            # Signing these binds the authorisation to one type and one exact
            # size. Drop either and the URL becomes permission to upload
            # anything of any size until it expires.
            "ContentType": content_type,
            "ContentLength": content_length,
        },
        ExpiresIn=expires_in,
    )

    return PresignedUpload(
        url=url,
        key=key,
        expires_in=expires_in,
        max_bytes=settings.R2_MAX_UPLOAD_BYTES,
    )


def promote_object(*, key: str, user_id: int) -> str:
    """Move a pending upload to its permanent home once an entry references it.

    Called when the entry is saved (E4). Until this runs, the object sits under
    `pending/` and the lifecycle rule will eventually reclaim it — which is the
    desired behaviour for an upload that never got attached to anything.

    Copy-then-delete rather than a move: S3-compatible storage has no atomic
    rename. The copy happens server-side inside R2, so no bytes cross the
    network and there is no egress charge. If the delete fails after a
    successful copy the object exists in both places, which the lifecycle rule
    then cleans up on its own — the failure mode is a duplicate for a few days,
    not a lost photo.

    `user_id` is required and checked rather than parsed from the key, because
    the key arrives from the client. Without this, a caller could hand over
    another user's pending key and have it promoted into their own namespace.
    """
    expected_prefix = f"{PENDING_PREFIX}{user_id}/"
    if not key.startswith(expected_prefix):
        raise ValidationError({"key": ["Not a pending upload belonging to this user."]})

    permanent_key = f"{ENTRIES_PREFIX}{key.removeprefix(PENDING_PREFIX)}"
    client = _client()
    bucket = settings.R2_BUCKET_NAME

    client.copy_object(
        Bucket=bucket,
        Key=permanent_key,
        CopySource={"Bucket": bucket, "Key": key},
    )
    client.delete_object(Bucket=bucket, Key=key)

    return permanent_key


def _transfer_object(*, key: str, destination: str) -> None:
    client = _client()
    bucket = settings.R2_BUCKET_NAME
    client.copy_object(Bucket=bucket, Key=destination, CopySource={"Bucket": bucket, "Key": key})
    client.delete_object(Bucket=bucket, Key=key)


def retain_analysis_object(*, key: str, user_id: int) -> str:
    """Move an admitted analysis image outside pending lifecycle cleanup."""
    expected_prefix = f"{PENDING_PREFIX}{user_id}/"
    if not key.startswith(expected_prefix):
        raise ValidationError({"photo_key": ["Not a pending upload belonging to this user."]})
    retained = f"{ANALYSES_PREFIX}{key.removeprefix(PENDING_PREFIX)}"
    _transfer_object(key=key, destination=retained)
    return retained


def copy_analysis_object_to_entry(*, key: str, user_id: int) -> str:
    """Copy a retained analysis image to its future entry key without deleting the source."""
    expected_prefix = f"{ANALYSES_PREFIX}{user_id}/"
    if not key.startswith(expected_prefix):
        raise ValidationError({"analysis": ["The analysis photo does not belong to this user."]})
    destination = f"{ENTRIES_PREFIX}{key.removeprefix(ANALYSES_PREFIX)}"
    client = _client()
    bucket = settings.R2_BUCKET_NAME
    client.copy_object(
        Bucket=bucket,
        Key=destination,
        CopySource={"Bucket": bucket, "Key": key},
    )
    return destination


def delete_object(*, key: str) -> None:
    """Delete one exact object key after its durable replacement is committed."""
    _client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)


def presign_download(*, key: str) -> str:
    """Mint a time-limited read URL for an object.

    Deliberately takes a key and no user: ownership is the caller's to check.
    This function cannot tell whether the requester owns the key, and quietly
    assuming they do would turn any endpoint that reaches it into a way to read
    another user's photos by guessing a prefix.
    """
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=settings.R2_DOWNLOAD_URL_EXPIRY_SECONDS,
    )
