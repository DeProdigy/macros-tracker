"""Tests for POST /api/auth/sessions/.

The verifier is stubbed rather than re-exercised. It has 49 tests of its own in
test_apple_identity.py, and this ticket is about what happens *after* it returns
a set of claims. Stubbing it also means these tests state their inputs as claims,
which is what the resolution logic actually branches on.

Two assertions here carry most of the weight. The first is that a second sign-in
without an email or a name leaves both stored values alone: that is the bug doc
04 warns about, it cannot appear until a real user comes back, and by then it
has silently erased a working address. The second is that every distinct
verification failure produces an identical response, because a 401 that
distinguishes "wrong audience" from "bad signature" is a free oracle.
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from accounts import services
from accounts.models import Identity, User
from accounts.throttles import SignInBurstThrottle, SignInSustainedThrottle

APPLE_SUB = "000123.abcdef.4567"
RAW_NONCE = "raw-nonce-for-this-attempt"


def claims(**overrides) -> services.AppleClaims:
    defaults = {
        "subject": APPLE_SUB,
        "email": "user@example.com",
        "is_private_email": False,
        "real_user_status": Identity.RealUserStatus.LIKELY_REAL,
    }
    return services.AppleClaims(**{**defaults, **overrides})


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle state lives in the cache and outlives a test.

    Without this the sixth test in a class starts pre-throttled, and the
    failures look like unrelated 429s in whichever test happens to run last.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def verifier(monkeypatch):
    """Stub the verifier. Returns a handle so a test can change the claims."""

    class Stub:
        def __init__(self):
            self.claims = claims()
            self.calls: list[tuple[str, str]] = []

        def __call__(self, token, *, expected_nonce):
            self.calls.append((token, expected_nonce))
            return self.claims

    stub = Stub()
    monkeypatch.setattr(services, "verify_apple_identity_token", stub)
    return stub


@pytest.fixture
def api_client() -> APIClient:
    """Not named `client`: that would shadow pytest-django's own fixture."""
    return APIClient()


@pytest.fixture
def url() -> str:
    return reverse("accounts:session-create")


def sign_in(api_client, url, **extra):
    body = {"identity_token": "any.jwt.here", "nonce": RAW_NONCE, **extra}
    return api_client.post(url, body, format="json")


# --- creating an account ------------------------------------------------------


@pytest.mark.django_db
def test_first_sign_in_creates_the_user(api_client, url, verifier):
    response = sign_in(api_client, url, name="Alex Hint")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["created"] is True
    assert response.data["access"]
    assert response.data["refresh"]
    assert response.data["user"]["email"] == "user@example.com"
    assert response.data["user"]["name"] == "Alex Hint"

    user = User.objects.get()
    identity = user.identities.get()
    assert identity.subject == APPLE_SUB
    assert identity.real_user_status == Identity.RealUserStatus.LIKELY_REAL


@pytest.mark.django_db
def test_the_raw_nonce_reaches_the_verifier(api_client, url, verifier):
    """Guards the MAC-30 contract. The client sends the raw value and the
    server hashes it; forwarding a digest here would double-hash."""
    sign_in(api_client, url)

    assert verifier.calls == [("any.jwt.here", RAW_NONCE)]


@pytest.mark.django_db
def test_sign_in_without_an_email_claim_creates_the_user(api_client, url, verifier):
    verifier.claims = claims(email=None)

    response = sign_in(api_client, url)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["user"]["email"] is None


@pytest.mark.django_db
def test_two_users_without_emails_coexist(api_client, url, verifier):
    """The nullable-unique trick, exercised through the endpoint rather than
    the manager. Postgres treats NULLs as distinct."""
    verifier.claims = claims(subject="000111.aaa.1111", email=None)
    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED

    verifier.claims = claims(subject="000222.bbb.2222", email=None)
    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED

    assert User.objects.filter(email__isnull=True).count() == 2


# --- returning ----------------------------------------------------------------


@pytest.mark.django_db
def test_returning_sign_in_reuses_the_same_user(api_client, url, verifier):
    first = sign_in(api_client, url, name="Alex Hint")
    second = sign_in(api_client, url)

    assert first.data["created"] is True
    assert second.data["created"] is False
    assert second.data["user"]["id"] == first.data["user"]["id"]
    assert User.objects.count() == 1
    assert Identity.objects.count() == 1


@pytest.mark.django_db
def test_second_sign_in_without_email_or_name_keeps_both(api_client, url, verifier):
    """The bug doc 04 warns about, and the reason this endpoint is not a
    straight upsert.

    Apple omits the email claim for real users and never resends the name after
    the first authorization. Writing those absences through would erase a
    working address on somebody's second login -- invisible until a real user
    comes back, and unrecoverable once it happens.
    """
    sign_in(api_client, url, name="Alex Hint")

    verifier.claims = claims(email=None)
    response = sign_in(api_client, url)

    assert response.data["user"]["email"] == "user@example.com"
    assert response.data["user"]["name"] == "Alex Hint"


@pytest.mark.django_db
def test_a_changed_relay_address_is_written_through(api_client, url, verifier):
    """Absent means "no change"; present and different means a real change.
    A Hide My Email relay can rotate."""
    sign_in(api_client, url)

    verifier.claims = claims(email="new-relay@privaterelay.appleid.com")
    response = sign_in(api_client, url)

    assert response.data["user"]["email"] == "new-relay@privaterelay.appleid.com"


@pytest.mark.django_db
def test_a_name_sent_later_is_stored(api_client, url, verifier):
    """Not the normal path, but a reinstalled app after revoking the Apple
    permission does send it again."""
    sign_in(api_client, url)

    response = sign_in(api_client, url, name="Alex Hint")

    assert response.data["user"]["name"] == "Alex Hint"


@pytest.mark.django_db
def test_every_sign_in_stamps_both_timestamps(api_client, url, verifier):
    sign_in(api_client, url)

    user = User.objects.get()
    assert user.last_login is not None
    assert user.identities.get().last_authenticated_at is not None


# --- reactivation -------------------------------------------------------------


@pytest.mark.django_db
def test_a_deleted_user_is_restored_not_duplicated(api_client, url, verifier):
    """The row still holds their unique (provider, subject) pair, so a naive
    create would collide on the constraint *and* fork a second account."""
    sign_in(api_client, url, name="Alex Hint")
    user = User.objects.get()
    User.objects.filter(pk=user.pk).update(deleted_at=timezone.now(), is_active=False)

    response = sign_in(api_client, url)

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["user"]["id"] == user.pk
    assert User.objects.count() == 1

    user.refresh_from_db()
    assert user.deleted_at is None
    assert user.is_active is True
    assert user.name == "Alex Hint"


@pytest.mark.django_db
def test_reactivation_has_no_time_limit(api_client, url, verifier):
    """The rewritten rule. A deletion older than any grace period still
    restores, because the purge enforces the deadline by deleting the row --
    and if the row is here, the purge has not run.

    The original spec refused past 30 days. That branch was unreachable in a
    working system: it could only trigger when the purge was broken, which is
    not a thing to tell a user about.
    """
    sign_in(api_client, url)
    user = User.objects.get()
    long_ago = timezone.now() - timedelta(days=365)
    User.objects.filter(pk=user.pk).update(deleted_at=long_ago, is_active=False)

    response = sign_in(api_client, url)

    assert response.status_code == status.HTTP_201_CREATED
    user.refresh_from_db()
    assert user.deleted_at is None


@pytest.mark.django_db
def test_a_purged_user_gets_a_clean_account(api_client, url, verifier):
    """Once the purge removes the row, sign-in takes the create branch. Same
    behaviour accepted for a deleted Apple ID in MAC-35."""
    sign_in(api_client, url, name="Alex Hint")
    User.objects.all().delete()

    response = sign_in(api_client, url)

    assert response.data["created"] is True
    assert response.data["user"]["name"] == ""


# --- rejection ----------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "code",
    [
        "invalid_signature",
        "invalid_audience",
        "invalid_issuer",
        "token_expired",
        "nonce_mismatch",
        "unknown_key",
        "unusable_key",
        "malformed_token",
        "jwks_unavailable",
    ],
)
def test_every_verification_failure_looks_identical(api_client, url, monkeypatch, code):
    """The oracle test. Each of these is a distinct code inside the verifier so
    its own suite can prove the check runs; none may be distinguishable here."""

    def reject(token, *, expected_nonce):
        raise ValidationError({"identity_token": ["nope"]}, code=code)

    monkeypatch.setattr(services, "verify_apple_identity_token", reject)

    response = sign_in(api_client, url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["detail"] == "Could not verify the Apple credential."
    assert response.data["detail"].code == "invalid_apple_credential"
    assert not User.objects.exists()


@pytest.mark.django_db
def test_rejection_is_401_and_not_403(api_client, url, monkeypatch):
    """Regression guard for the DRF behaviour this endpoint had to work around.

    `authentication_classes = []` makes DRF rewrite AuthenticationFailed to 403,
    so InvalidAppleCredential is a plain APIException instead. Switching it back
    to AuthenticationFailed would silently turn every failed sign-in into a 403.
    """

    def reject(token, *, expected_nonce):
        raise ValidationError({"identity_token": ["nope"]}, code="invalid_signature")

    monkeypatch.setattr(services, "verify_apple_identity_token", reject)

    assert sign_in(api_client, url).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
@pytest.mark.parametrize("missing", ["identity_token", "nonce"])
def test_a_missing_field_is_400_before_anything_else(api_client, url, verifier, missing):
    """Serializer validation runs first, so a malformed body never reaches the
    verifier or the database."""
    body = {"identity_token": "any.jwt.here", "nonce": RAW_NONCE}
    body.pop(missing)

    response = api_client.post(url, body, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert verifier.calls == []
    assert not User.objects.exists()


# --- access -------------------------------------------------------------------


@pytest.mark.django_db
def test_the_endpoint_is_reachable_without_authentication(api_client, url, verifier):
    """The AllowAny opt-out, asserted rather than assumed. The project default
    is IsAuthenticated, which would 401 the request that creates the session."""
    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_the_returned_access_token_authenticates(api_client, url, verifier):
    """The minted pair actually resolves back to this user.

    Driven through JWTAuthentication rather than by calling some other
    authenticated endpoint. The only ones that exist are uploads, which would
    drag boto3 and R2 credentials into a test about tokens -- a failure there
    would look like a broken token.
    """
    response = sign_in(api_client, url)
    user = User.objects.get()

    request = APIRequestFactory().get("/")
    request.META["HTTP_AUTHORIZATION"] = f"Bearer {response.data['access']}"
    # authenticate() returns None when it finds no credentials at all, which
    # would make the unpack below fail with a less useful error than this.
    result = JWTAuthentication().authenticate(request)
    assert result is not None

    authenticated, _ = result
    assert authenticated == user


@pytest.mark.django_db
def test_the_refresh_token_is_outstanding(api_client, url, verifier):
    """Proves rotation and sign-out have something to blacklist later. A
    refresh token missing from the outstanding table cannot be revoked."""
    response = sign_in(api_client, url)
    user = User.objects.get()

    assert OutstandingToken.objects.filter(user=user).exists()
    assert response.data["refresh"]


# --- throttling ---------------------------------------------------------------


@pytest.fixture
def rates(monkeypatch):
    """Override the throttle rates for one test.

    Not via `settings.REST_FRAMEWORK`, which silently does nothing here.
    `SimpleRateThrottle.THROTTLE_RATES` is a *class* attribute bound to the
    settings dict at import time, so a later override creates a new dict the
    class never looks at. Production is unaffected -- the class body runs after
    settings are configured, so it binds the real rates -- but a test that
    changed settings would pass while asserting nothing.

    Rates are lowered rather than looping to the real 10/min, which would make
    these the slowest tests in the suite for no extra assurance.
    """

    def apply(**overrides):
        table = {"signin-burst": "100/min", "signin-sustained": "1000/hour", **overrides}
        for throttle in (SignInBurstThrottle, SignInSustainedThrottle):
            monkeypatch.setattr(throttle, "THROTTLE_RATES", table)

    return apply


@pytest.mark.django_db
def test_the_burst_throttle_fires(api_client, url, verifier, rates):
    rates(**{"signin-burst": "2/min"})

    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED
    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED
    assert sign_in(api_client, url).status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_the_sustained_throttle_fires_independently(api_client, url, verifier, rates):
    """Both scopes apply and the slower is not shadowed by the faster. One flat
    rate cannot say "a burst is fine, all day is not"."""
    rates(**{"signin-sustained": "2/hour"})

    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED
    assert sign_in(api_client, url).status_code == status.HTTP_201_CREATED
    assert sign_in(api_client, url).status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_a_throttled_request_creates_nothing(api_client, url, verifier, rates):
    """429 has to fire before the handler, not after. A throttle that rejects
    the response but keeps the side effect is not a throttle."""
    rates(**{"signin-burst": "1/min"})

    sign_in(api_client, url)
    assert sign_in(api_client, url).status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert User.objects.count() == 1
