"""Tests that the JWT machinery is actually wired up.

Nothing here tests simplejwt itself. These exist to catch the configuration
mistakes that are invisible until a much later ticket tries to use them: the
blacklist app missing from INSTALLED_APPS, its migrations never applied, or
rotation silently disabled. Without them, a missing app surfaces in MAC-28 as
"logout does nothing" rather than here as a failing test.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


@pytest.fixture
def apple_user(db):
    return User.objects.create_apple_user(apple_user_id="000123.abc.4567")


@pytest.mark.django_db
def test_refresh_token_can_be_issued_for_an_apple_user(apple_user):
    """An Apple user has no usable password, so this proves token issuance does
    not depend on one."""
    refresh = RefreshToken.for_user(apple_user)

    assert str(refresh)
    assert str(refresh.access_token)


@pytest.mark.django_db
def test_blacklisting_a_refresh_token_persists(apple_user):
    """Proves token_blacklist is installed and migrated.

    `.blacklist()` raises AttributeError when the app is missing, and simplejwt
    swallows exactly that exception during rotation -- so a missing app would
    make rotation quietly stop blacklisting anything.
    """
    refresh = RefreshToken.for_user(apple_user)

    refresh.blacklist()

    outstanding = OutstandingToken.objects.get(jti=refresh["jti"])
    assert BlacklistedToken.objects.filter(token=outstanding).exists()


@pytest.mark.django_db
def test_rotation_settings_are_on():
    """The two settings that make a stolen refresh token stop working once the
    real client refreshes. Both default to False in simplejwt."""
    from rest_framework_simplejwt.settings import api_settings

    assert api_settings.ROTATE_REFRESH_TOKENS
    assert api_settings.BLACKLIST_AFTER_ROTATION
