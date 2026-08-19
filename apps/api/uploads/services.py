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
    """Namespace an object under the owning user: `entries/{user_id}/{uuid}.ext`.

    The user_id prefix is what makes account deletion tractable — enumerate and
    purge by prefix rather than tracking every object individually in the
    database and hoping the two never diverge.

    The filename is a UUID rather than anything client-supplied. Client
    filenames invite collisions between users, path traversal via `../`, and
    leaking whatever the photo was called on someone's phone.
    """
    extension = settings.R2_ALLOWED_UPLOAD_TYPES[content_type]
    return f"entries/{user_id}/{uuid.uuid4()}.{extension}"


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
