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

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

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
