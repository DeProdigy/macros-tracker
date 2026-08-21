"""Tests for DELETE /api/users/me/.

Three things carry the weight here.

The first is that the deletion actually locks the account *now*. A test that
only asserts `deleted_at` is set proves nothing about access: no authentication
path reads that column. The test that matters reuses the same access token
afterwards and expects a 401.

The second is the refresh path, which fails for a different reason and would
keep working if only `is_active` were flipped -- the token itself is still
valid, so the blacklist is what stops it.

The third is idempotency. A retried DELETE must not push `deleted_at` forward,
because that column is the input to a retention deadline that a later ticket
enforces.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import services

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_apple_user(
        apple_user_id="000123.abc.4567",
        email="user@example.com",
    )


@pytest.fixture
def api_client() -> APIClient:
    """Not named `client`: that would shadow pytest-django's own fixture."""
    return APIClient()


@pytest.fixture
def refresh(user) -> RefreshToken:
    """One refresh token, and the access token in `authed_client` comes from it.

    Minting them together is the realistic shape -- a signed-in client holds a
    pair from one sign-in -- and it lets one test assert on both halves.
    """
    return RefreshToken.for_user(user)


@pytest.fixture
def authed_client(api_client, refresh) -> APIClient:
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def url() -> str:
    return reverse("users:current")


# --- the delete itself ------------------------------------------------------


@pytest.mark.django_db
def test_delete_soft_deletes_and_returns_204(authed_client, url, user):
    response = authed_client.delete(url)

    assert response.status_code == status.HTTP_204_NO_CONTENT

    user.refresh_from_db()
    assert user.deleted_at is not None
    assert user.is_active is False


@pytest.mark.django_db
def test_delete_401s_without_a_token(api_client, url, user):
    response = api_client.delete(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    user.refresh_from_db()
    assert user.deleted_at is None


@pytest.mark.django_db
def test_the_user_row_survives(authed_client, url, user):
    """Soft delete. The row is the only thing reactivation has to find."""
    authed_client.delete(url)

    assert User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_the_identity_survives(authed_client, url, user):
    """Sign-in resolves `(provider, subject)`, so deleting the Identity would
    turn every return visit into a second account rather than a restore."""
    authed_client.delete(url)

    assert user.identities.count() == 1


# --- access stops immediately -----------------------------------------------


@pytest.mark.django_db
def test_the_access_token_stops_working_at_once(authed_client, url):
    """The acceptance criterion this ticket exists for.

    Nothing on the access path consults a blacklist, so an access token cannot
    be revoked. `is_active=False` is what rejects it instead -- simplejwt's
    `JWTAuthentication` checks the flag on every request. Without that write,
    the same token below keeps reading and writing the account for up to the
    15-minute access lifetime.
    """
    assert authed_client.delete(url).status_code == status.HTTP_204_NO_CONTENT

    response = authed_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_the_refresh_token_cannot_mint_a_new_access_token(authed_client, url, refresh):
    """The other half, and it fails for a different reason.

    Refresh is a token exchange: it does not authenticate the user, so
    `is_active` never comes into it. The blacklist entry is the only thing
    standing between a stored refresh token and a fresh access token.
    """
    authed_client.delete(url)

    response = APIClient().post(
        reverse("accounts:session-refresh"),
        {"refresh": str(refresh)},
        format="json",
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_every_outstanding_refresh_token_is_blacklisted(authed_client, url, user, refresh):
    """Not just the one the caller happens to be using.

    A user can be signed in on more than one device, and this request carries
    no refresh token at all -- so the revocation has to be driven from the
    user, not from the presented credential.
    """
    second = RefreshToken.for_user(user)
    third = RefreshToken.for_user(user)

    authed_client.delete(url)

    blacklisted = set(
        BlacklistedToken.objects.filter(token__user=user).values_list("token__jti", flat=True)
    )
    assert blacklisted == {t["jti"] for t in (refresh.payload, second.payload, third.payload)}


@pytest.mark.django_db
def test_another_users_tokens_are_untouched(authed_client, url):
    """The filter is on the caller, and a missing `filter()` here would sign
    the whole user base out at once."""
    bystander = User.objects.create_apple_user(apple_user_id="000999.xyz.0001")
    RefreshToken.for_user(bystander)

    authed_client.delete(url)

    assert not BlacklistedToken.objects.filter(token__user=bystander).exists()
    bystander.refresh_from_db()
    assert bystander.is_active is True


# --- idempotency ------------------------------------------------------------


@pytest.mark.django_db
def test_deleting_twice_does_not_move_the_timestamp(authed_client, url, user):
    """`deleted_at` is the input to a retention deadline. A retried request
    that pushes it forward silently extends how long the data is kept.

    The second call goes through the service rather than the endpoint because
    the endpoint is unreachable once the account is deactivated -- which is
    itself the point of the test above.
    """
    authed_client.delete(url)
    user.refresh_from_db()
    first = user.deleted_at

    assert services.delete_account(user) is False

    user.refresh_from_db()
    assert user.deleted_at == first


@pytest.mark.django_db
def test_a_stale_user_instance_cannot_re_delete(user):
    """The guard re-reads the row instead of trusting the caller's copy.

    `request.user` is a snapshot taken when `JWTAuthentication` authenticated
    the request, so its `deleted_at` says what was true then. Two DELETEs
    arriving together would each hold a copy reading None. Updating the row
    behind this instance reproduces exactly that, without needing two threads.
    """
    stamped = timezone.now() - timedelta(minutes=5)
    User.objects.filter(pk=user.pk).update(deleted_at=stamped, is_active=False)
    assert user.deleted_at is None  # the stale copy, which is the whole point

    assert services.delete_account(user) is False

    user.refresh_from_db()
    assert user.deleted_at == stamped


@pytest.mark.django_db
def test_deletion_survives_an_already_blacklisted_token(user):
    """A plain `create` raises on the unique constraint and rolls the whole
    deletion back. Signing out before deleting is the ordinary way to reach that
    row, and the `blacklistedtoken__isnull=True` filter is what skips it."""
    token = RefreshToken.for_user(user)
    token.blacklist()

    assert services.delete_account(user) is True

    user.refresh_from_db()
    assert user.is_active is False
    assert BlacklistedToken.objects.filter(token__jti=token.payload["jti"]).count() == 1


@pytest.mark.django_db
def test_a_stale_outstanding_row_is_still_blacklisted(user):
    """An expired token is still an outstanding row until the flush command
    clears it, and blacklisting it is harmless. Asserted so a future change
    that skips rows by expiry has to argue for itself."""
    RefreshToken.for_user(user)
    OutstandingToken.objects.filter(user=user).update(
        expires_at=timezone.now() - timedelta(days=365)
    )

    services.delete_account(user)

    assert not OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).exists()


# --- the seam with MAC-27 ---------------------------------------------------


@pytest.mark.django_db
def test_a_deleted_account_is_restored_by_signing_in_again(authed_client, url, user):
    """The endpoint's description promises this, so a test holds it.

    Reactivation lives in `resolve_apple_user` (MAC-27). Called directly here:
    the full sign-in path needs a signed Apple token, and this test is about
    the delete side of the seam.
    """
    authed_client.delete(url)

    identity = user.identities.get()
    resolved = services.resolve_apple_user(
        services.AppleClaims(
            subject=identity.subject,
            email="user@example.com",
            is_private_email=None,
            real_user_status=None,
        )
    )

    assert resolved.reactivated is True
    assert resolved.created is False
    assert resolved.user.pk == user.pk

    user.refresh_from_db()
    assert user.deleted_at is None
    assert user.is_active is True
