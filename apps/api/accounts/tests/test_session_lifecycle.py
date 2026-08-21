"""Tests for refreshing and deleting a session.

Almost nothing here tests simplejwt. It tests the two claims this ticket makes
that are easy to believe and easy to get wrong.

The first is that rotation is a security property and not a setting somebody
turned on: a rotated refresh token must be *rejected on reuse*. Without that
assertion, `ROTATE_REFRESH_TOKENS = True` proves only that the response contains
a second string.

The second is that refresh works with no credentials at all. It has to -- it is
reached because the access token expired -- and the failure mode if it does not
is a client that can never recover from a 15-minute-old token without making the
user sign in again.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.throttles import RefreshThrottle

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_apple_user(apple_user_id="000123.abc.4567")


@pytest.fixture
def other_user(db):
    return User.objects.create_apple_user(apple_user_id="000999.zzz.0000")


@pytest.fixture
def api_client() -> APIClient:
    """Not named `client`: that would shadow pytest-django's own fixture."""
    return APIClient()


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Refresh is throttled, and throttle state outlives a test.

    Without this the tests that refresh repeatedly start leaking 429s into
    whichever test happens to run last, which looks like anything but a
    throttle.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def tokens(user) -> RefreshToken:
    return RefreshToken.for_user(user)


def authenticated(api_client: APIClient, refresh: RefreshToken) -> APIClient:
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


# --- POST /api/auth/sessions/refresh/ ---------------------------------------


@pytest.mark.django_db
def test_refresh_returns_a_new_pair(api_client, tokens):
    response = api_client.post(
        reverse("accounts:session-refresh"),
        {"refresh": str(tokens)},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["access"]
    assert response.data["refresh"]


@pytest.mark.django_db
def test_refresh_rotates_the_refresh_token(api_client, tokens):
    """The returned refresh token is a *different* token.

    If this ever comes back equal, rotation is off and the long-lived credential
    now never changes for 30 days.
    """
    presented = str(tokens)

    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": presented})

    assert response.data["refresh"] != presented


@pytest.mark.django_db
def test_a_rotated_refresh_token_is_rejected_on_reuse(api_client, tokens):
    """The assertion that makes rotation worth having.

    Reuse of an already-rotated token is the observable signature of a stolen
    credential. Rotation without blacklisting detects nothing and revokes
    nothing -- it just hands out extra tokens.
    """
    presented = str(tokens)
    api_client.post(reverse("accounts:session-refresh"), {"refresh": presented})

    reused = api_client.post(reverse("accounts:session-refresh"), {"refresh": presented})

    assert reused.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_needs_no_authorization_header(api_client, tokens):
    """The deadlock test.

    The endpoint exists because the access token expired. Requiring a valid one
    would make an expired session unrecoverable, and the mistake is invisible in
    any test that happens to send a header.
    """
    api_client.credentials()  # explicit: no Authorization header

    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": str(tokens)})

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_refresh_rejects_a_garbage_token(api_client):
    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": "not-a-jwt"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_rejects_an_expired_token(api_client, tokens):
    """Well-formed and past its expiry, which is what happens to real users.

    The garbage-token test above proves the parser rejects nonsense. It says
    nothing about the 30-day lifetime, and expiry is the case every user
    eventually hits. The token is minted valid and then backdated past its own
    expiry rather than waiting a month.
    """
    tokens.set_exp(from_time=tokens.current_time - timedelta(days=31))

    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": str(tokens)})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_401s_when_the_token_outlived_its_user(api_client, user, tokens):
    """A valid token whose user row is gone. Was a 500.

    simplejwt looks the user up with a bare `.get()`, and `User.DoesNotExist` is
    not an APIException, so DRF hands it to the 500 handler. Nothing in the app
    hard-deletes a user yet -- the admin's delete button is what reaches this
    today, and MAC-29 would otherwise inherit a 500 it did not write.
    """
    presented = str(tokens)
    User.objects.filter(pk=user.pk).delete()

    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": presented})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_401s_for_a_deactivated_user(api_client, user, tokens):
    """Deactivation revokes refresh, for free, via simplejwt's
    USER_AUTHENTICATION_RULE.

    Pinned rather than assumed. It is the property MAC-29 has to decide whether
    account deletion should lean on, and "it already works" is worth being a
    stated fact by then rather than something rediscovered.

    Note the third state does *not* behave this way: `deleted_at` alone still
    refreshes, because nothing on this path reads it. That is MAC-29's to close.
    """
    user.is_active = False
    user.save()

    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": str(tokens)})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_refresh_is_throttled(api_client, user, monkeypatch):
    """The endpoint is unauthenticated, so it has a limit.

    The rate is lowered by patching `THROTTLE_RATES` on the class, not by
    overriding `settings.REST_FRAMEWORK`. `SimpleRateThrottle.THROTTLE_RATES` is
    a class attribute bound to the settings dict at import time, so a settings
    override builds a new dict the class never reads and the test passes while
    asserting nothing. Same trap as the sign-in throttle tests.

    A fresh token per call, because rotation blacklists the last one and a 401
    would satisfy nothing here.
    """
    monkeypatch.setattr(RefreshThrottle, "THROTTLE_RATES", {"refresh": "1/min"})
    url = reverse("accounts:session-refresh")
    first = api_client.post(url, {"refresh": str(RefreshToken.for_user(user))})

    second = api_client.post(url, {"refresh": str(RefreshToken.for_user(user))})

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_refresh_requires_the_field(api_client):
    response = api_client.post(reverse("accounts:session-refresh"), {})

    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --- DELETE /api/auth/sessions/current/ -------------------------------------


@pytest.mark.django_db
def test_sign_out_blacklists_the_presented_token(api_client, user, tokens):
    response = authenticated(api_client, tokens).delete(
        reverse("accounts:session-current"),
        {"refresh": str(tokens)},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    outstanding = OutstandingToken.objects.get(jti=tokens["jti"])
    assert BlacklistedToken.objects.filter(token=outstanding).exists()


@pytest.mark.django_db
def test_a_signed_out_token_can_no_longer_refresh(api_client, user, tokens):
    """What sign-out actually buys, stated as behaviour rather than as a row.

    Note what it does *not* buy: the access token the client is holding stays
    valid until it expires. Nothing on the access path consults the blacklist,
    which is the whole reason access lifetimes are 15 minutes.
    """
    presented = str(tokens)
    authenticated(api_client, tokens).delete(
        reverse("accounts:session-current"),
        {"refresh": presented},
    )

    api_client.credentials()
    response = api_client.post(reverse("accounts:session-refresh"), {"refresh": presented})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_sign_out_requires_authentication(api_client, tokens):
    response = api_client.delete(
        reverse("accounts:session-current"),
        {"refresh": str(tokens)},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_sign_out_refuses_another_users_token(api_client, user, other_user, tokens):
    """Otherwise sign-out is a denial of service on anybody else's session.

    An authenticated caller who gets hold of a refresh token could end the
    session it belongs to. The token stays usable.
    """
    victim = RefreshToken.for_user(other_user)

    response = authenticated(api_client, tokens).delete(
        reverse("accounts:session-current"),
        {"refresh": str(victim)},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    outstanding = OutstandingToken.objects.get(jti=victim["jti"])
    assert not BlacklistedToken.objects.filter(token=outstanding).exists()


@pytest.mark.django_db
def test_signing_out_twice_reports_the_token_is_gone(api_client, user, tokens):
    """Second call returns 400, not 500.

    The client's correct behaviour is identical either way -- clear the Keychain
    -- so this asserts the endpoint stays boring rather than that it is
    idempotent in the strict sense.
    """
    presented = str(tokens)
    client = authenticated(api_client, tokens)
    client.delete(reverse("accounts:session-current"), {"refresh": presented})

    response = client.delete(reverse("accounts:session-current"), {"refresh": presented})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
