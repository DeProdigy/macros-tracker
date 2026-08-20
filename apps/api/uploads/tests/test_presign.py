"""Tests for presigned upload authorisation.

A presigned URL is a credential this API mints on request, so the assertions
that carry the weight are the ones proving it refuses: wrong type, oversize,
unauthenticated, and another user's namespace. A test suite that only proves
the happy path proves that the endpoint signs things, which was never in doubt.

Nothing here talks to Cloudflare. boto3 signs locally with no network call, so
the URLs are real signatures over fake credentials — which is exactly what makes
these hermetic and still meaningful.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from uploads import services

User = get_user_model()

# Fake but well-formed: boto3 validates the shape of credentials while signing.
R2_TEST_SETTINGS = {
    "R2_ACCOUNT_ID": "testaccount",
    "R2_BUCKET_NAME": "test-bucket",
    "R2_ACCESS_KEY_ID": "testaccesskeyid",
    "R2_SECRET_ACCESS_KEY": "testsecretaccesskey",
    "R2_ENDPOINT_URL": "https://testaccount.r2.cloudflarestorage.com",
}


@pytest.fixture(autouse=True)
def r2_settings(settings):
    """Applied to every test: signing fails without credentials, and the real
    ones must never be required to run the suite."""
    for key, value in R2_TEST_SETTINGS.items():
        setattr(settings, key, value)
    return settings


@pytest.fixture
def user(db):
    return User.objects.create_user(email="owner@example.com", password="pw-not-real-12345")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="other@example.com", password="pw-not-real-12345")


@pytest.fixture
def api_client() -> APIClient:
    """Not named `client`: that would shadow pytest-django's own fixture."""
    return APIClient()


@pytest.fixture
def auth_client(api_client: APIClient, user) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client


def presign(client: APIClient, **overrides):
    payload = {"content_type": "image/jpeg", "content_length": 1024}
    payload.update(overrides)
    return client.post(reverse("uploads:create"), payload, format="json")


# --- Authentication ---------------------------------------------------------


def test_presign_requires_authentication(api_client: APIClient, db):
    """An open presign endpoint is an anonymous write handle to the bucket."""
    response = presign(api_client)

    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )


def test_presign_does_not_sign_anything_for_anonymous_callers(api_client: APIClient, db):
    """Rejection must happen before signing — a URL in the body of a 401 is
    still a usable credential."""
    response = presign(api_client)

    assert "url" not in response.json()


# --- Content type validation ------------------------------------------------


@pytest.mark.parametrize(
    "content_type",
    ["application/pdf", "text/html", "application/octet-stream", "image/svg+xml", ""],
)
def test_presign_rejects_unsupported_content_types(auth_client: APIClient, content_type: str):
    """The allowlist is the bucket's only defence against arbitrary content.
    image/svg+xml is in this list on purpose: SVGs execute script, so an image/*
    prefix check rather than an allowlist would let one through."""
    response = presign(auth_client, content_type=content_type)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_presign_rejects_unsupported_type_by_name(auth_client: APIClient):
    response = presign(auth_client, content_type="application/pdf")

    assert "content_type" in response.json()


@pytest.mark.parametrize("content_type", ["image/jpeg", "image/png", "image/webp", "image/heic"])
def test_presign_accepts_each_supported_image_type(auth_client: APIClient, content_type: str):
    """HEIC matters specifically: it is the iPhone camera default, and omitting
    it would reject the single most common real upload."""
    response = presign(auth_client, content_type=content_type)

    assert response.status_code == status.HTTP_200_OK


# --- Size validation --------------------------------------------------------


def test_presign_rejects_uploads_over_the_ceiling(auth_client: APIClient, settings):
    """Without a ceiling a client can PUT hundreds of megabytes and the bill
    arrives for storage nobody wanted."""
    response = presign(auth_client, content_length=settings.R2_MAX_UPLOAD_BYTES + 1)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "content_length" in response.json()


def test_presign_accepts_an_upload_exactly_at_the_ceiling(auth_client: APIClient, settings):
    """Boundary: the limit is inclusive, so a file of exactly max size works."""
    response = presign(auth_client, content_length=settings.R2_MAX_UPLOAD_BYTES)

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.parametrize("content_length", [0, -1])
def test_presign_rejects_non_positive_lengths(auth_client: APIClient, content_length: int):
    response = presign(auth_client, content_length=content_length)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_presign_requires_both_fields(auth_client: APIClient):
    """Defaulting either would mean signing constraints the client never
    committed to, which is the same as not constraining it."""
    response = auth_client.post(reverse("uploads:create"), {}, format="json")

    body = response.json()

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert set(body) == {"content_type", "content_length"}


# --- Object keys ------------------------------------------------------------


def test_key_is_namespaced_under_the_requesting_user(auth_client: APIClient, user):
    """The user_id prefix is what makes account deletion a prefix purge rather
    than a reconciliation between the bucket and the database."""
    key = presign(auth_client).json()["key"]

    assert key.startswith(f"pending/{user.pk}/")


def test_key_ignores_any_user_id_the_client_supplies(auth_client: APIClient, user, other_user):
    """The key comes from the session, never the payload. Otherwise any user
    could write into another user's namespace by asking."""
    response = presign(auth_client, user_id=other_user.pk)

    assert response.json()["key"].startswith(f"pending/{user.pk}/")


def test_key_extension_follows_the_declared_content_type(auth_client: APIClient):
    key = presign(auth_client, content_type="image/png").json()["key"]

    assert key.endswith(".png")


def test_keys_are_unique_across_requests(auth_client: APIClient):
    """Client filenames would collide and leak; a UUID does neither."""
    first = presign(auth_client).json()["key"]
    second = presign(auth_client).json()["key"]

    assert first != second


def test_key_contains_no_client_controlled_path_segments(auth_client: APIClient, user):
    """Guards against traversal: the key is built entirely from a user id, a
    UUID, and an extension chosen from the allowlist."""
    key = presign(auth_client).json()["key"]

    assert ".." not in key
    assert key.count("/") == 2


# --- The signed URL ---------------------------------------------------------


def test_response_has_exactly_the_documented_fields(auth_client: APIClient):
    """Extra or missing keys mean the generated client type lies."""
    body = presign(auth_client).json()

    assert set(body) == {"url", "key", "expires_in", "max_bytes"}


def test_url_points_at_the_configured_bucket_and_key(auth_client: APIClient, settings):
    body = presign(auth_client).json()
    parsed = urlparse(body["url"])

    assert settings.R2_BUCKET_NAME in parsed.path
    assert body["key"] in parsed.path


def test_url_uses_sigv4(auth_client: APIClient):
    """R2 rejects earlier signing versions, and the resulting error names
    neither the setting nor the signature version."""
    query = parse_qs(urlparse(presign(auth_client).json()["url"]).query)

    assert "AWS4-HMAC-SHA256" in query.get("X-Amz-Algorithm", [])


def test_url_expires_and_reports_a_matching_lifetime(auth_client: APIClient, settings):
    """A presigned URL is a bearer credential; an unbounded one is a permanent
    write grant to anyone who sees it."""
    body = presign(auth_client).json()
    query = parse_qs(urlparse(body["url"]).query)

    assert query["X-Amz-Expires"] == [str(settings.R2_UPLOAD_URL_EXPIRY_SECONDS)]
    assert body["expires_in"] == settings.R2_UPLOAD_URL_EXPIRY_SECONDS


def test_signature_covers_content_type_and_length(auth_client: APIClient):
    """The point of the whole design. Unsigned, these are suggestions the
    holder of the URL may ignore; signed, storage enforces them.
    """
    query = parse_qs(urlparse(presign(auth_client).json()["url"]).query)
    signed_headers = query["X-Amz-SignedHeaders"][0]

    assert "content-type" in signed_headers
    assert "content-length" in signed_headers


def test_max_bytes_is_echoed_so_clients_can_fail_fast(auth_client: APIClient, settings):
    assert presign(auth_client).json()["max_bytes"] == settings.R2_MAX_UPLOAD_BYTES


# --- Promotion --------------------------------------------------------------
#
# Uploads land under pending/ and only move to entries/ once something
# references them. The lifecycle rule expires pending/, so a promotion that
# silently fails means a photo deleted a week later.


def test_promote_moves_a_pending_key_to_the_entries_prefix(db, monkeypatch):
    calls = {}

    class FakeClient:
        def copy_object(self, **kwargs):
            calls["copy"] = kwargs

        def delete_object(self, **kwargs):
            calls["delete"] = kwargs

    monkeypatch.setattr(services, "_client", lambda: FakeClient())

    result = services.promote_object(key="pending/7/abc.jpg", user_id=7)

    assert result == "entries/7/abc.jpg"
    assert calls["copy"]["Key"] == "entries/7/abc.jpg"
    assert calls["copy"]["CopySource"]["Key"] == "pending/7/abc.jpg"
    assert calls["delete"]["Key"] == "pending/7/abc.jpg"


def test_promote_rejects_another_users_pending_key(db, monkeypatch):
    """The key arrives from the client. Parsing the owner out of it instead of
    checking it would let anyone promote someone else's upload into their own
    namespace just by passing the key."""
    monkeypatch.setattr(services, "_client", lambda: pytest.fail("must not reach storage"))

    with pytest.raises(ValidationError):
        services.promote_object(key="pending/999/abc.jpg", user_id=7)


def test_promote_rejects_a_key_outside_the_pending_prefix(db, monkeypatch):
    """Guards against promoting an already-permanent object, or anything the
    client invented, back through the copy path."""
    monkeypatch.setattr(services, "_client", lambda: pytest.fail("must not reach storage"))

    with pytest.raises(ValidationError):
        services.promote_object(key="entries/7/abc.jpg", user_id=7)


def test_promote_rejects_a_traversal_attempt(db, monkeypatch):
    monkeypatch.setattr(services, "_client", lambda: pytest.fail("must not reach storage"))

    with pytest.raises(ValidationError):
        services.promote_object(key="pending/7/../../etc/passwd", user_id=70)


def test_promoted_key_is_the_presigned_key_with_the_prefix_swapped(
    auth_client: APIClient, user, monkeypatch
):
    """End to end across both halves: whatever presign hands out must be
    promotable, or uploads silently expire after the lifecycle window."""

    class FakeClient:
        def copy_object(self, **kwargs):
            pass

        def delete_object(self, **kwargs):
            pass

    key = presign(auth_client).json()["key"]
    monkeypatch.setattr(services, "_client", lambda: FakeClient())

    promoted = services.promote_object(key=key, user_id=user.pk)

    assert promoted.startswith(f"entries/{user.pk}/")
    assert promoted.removeprefix("entries/") == key.removeprefix("pending/")


# --- Download presigning ----------------------------------------------------


def test_presign_download_returns_a_time_limited_url(db, settings):
    url = services.presign_download(key="entries/1/abc.jpg")
    query = parse_qs(urlparse(url).query)

    assert query["X-Amz-Expires"] == [str(settings.R2_DOWNLOAD_URL_EXPIRY_SECONDS)]


def test_download_urls_live_longer_than_upload_urls(settings):
    """Deliberate asymmetry: an upload is seconds of work, while a read may sit
    on screen in a list view for a while."""
    assert settings.R2_DOWNLOAD_URL_EXPIRY_SECONDS > settings.R2_UPLOAD_URL_EXPIRY_SECONDS


# --- Method routing ---------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
def test_presign_rejects_non_post_methods(auth_client: APIClient, method: str):
    """Only POST is declared in the schema, so only POST may be routed."""
    response = getattr(auth_client, method)(reverse("uploads:create"))

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# --- Emitted schema ---------------------------------------------------------


@pytest.fixture
def schema() -> dict:
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def test_schema_uses_the_explicit_operation_id(schema: dict):
    """Drives the generated hook name (`usePresignUpload`)."""
    assert schema["paths"]["/api/uploads/"]["post"]["operationId"] == "presignUpload"


def test_schema_requires_auth_for_presign(schema: dict):
    """The inverse of the ping/health assertion: an empty security requirement
    here would mean the schema advertises an open write endpoint."""
    security = schema["paths"]["/api/uploads/"]["post"].get("security", [])

    assert {} not in security


def test_schema_response_declares_all_fields(schema: dict):
    properties = schema["components"]["schemas"]["PresignUploadResponse"]["properties"]

    assert set(properties) == {"url", "key", "expires_in", "max_bytes"}


def test_schema_marks_request_fields_required(schema: dict):
    """Optional fields generate `T | undefined` and defeat compile-time safety."""
    component = schema["components"]["schemas"]["PresignUploadRequestRequest"]

    assert set(component["required"]) == {"content_type", "content_length"}
