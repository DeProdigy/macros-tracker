"""Tests for the custom User model and its manager.

RSpec equivalent: `spec/models/user_spec.rb`. These pin down the behaviour of
`UserManager.create_user` / `create_superuser`.

`@pytest.mark.django_db` grants a test access to the (rolled-back) test database
— the equivalent of RSpec's transactional fixtures. Tests without it must not
touch the DB, which is why the pure-guard cases below omit it.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


@pytest.mark.django_db
def test_create_user_normalizes_email_and_hashes_password():
    user = User.objects.create_user(email="Alice@EXAMPLE.com", password="s3cret")

    # normalize_email lowercases the domain; the local part is preserved.
    assert user.email == "Alice@example.com"
    # The password is stored hashed, never in plaintext.
    assert user.password != "s3cret"
    assert user.check_password("s3cret")


@pytest.mark.django_db
def test_create_user_sets_sensible_defaults():
    user = User.objects.create_user(email="bob@example.com", password="pw")

    assert not user.is_staff
    assert not user.is_superuser
    assert user.is_active
    assert not user.onboarding_completed
    assert user.timezone == "UTC"
    assert user.ai_calls_this_month == 0


def test_create_user_requires_an_email():
    # The guard raises before any DB access, so no django_db marker is needed.
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="pw")


@pytest.mark.django_db
def test_create_superuser_sets_staff_and_superuser_flags():
    admin = User.objects.create_superuser(email="admin@example.com", password="pw")

    assert admin.is_staff
    assert admin.is_superuser


def test_create_superuser_rejects_non_staff():
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="admin@example.com", password="pw", is_staff=False)


def test_create_superuser_rejects_non_superuser():
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="admin@example.com", password="pw", is_superuser=False)


@pytest.mark.django_db
def test_str_is_the_email():
    user = User.objects.create_user(email="carol@example.com", password="pw")

    assert str(user) == "carol@example.com"


# --- Apple users ------------------------------------------------------------
#
# create_apple_user is the path every real user of this app takes. It differs
# from create_user in the two ways Sign in with Apple forces: there is no
# password to set, and there may be no email to store.


@pytest.mark.django_db
def test_create_apple_user_stores_the_subject_and_no_password():
    user = User.objects.create_apple_user(apple_user_id="000123.abc.4567")

    assert user.apple_user_id == "000123.abc.4567"
    assert user.email is None
    # Unusable is stronger than blank: no input matches, not even the stored
    # value, so there is nothing to brute force.
    assert not user.has_usable_password()
    assert not user.check_password("")


@pytest.mark.django_db
def test_create_apple_user_normalizes_a_supplied_email():
    user = User.objects.create_apple_user(
        apple_user_id="000123.abc.4567", email="Relay@PRIVATERELAY.appleid.com"
    )

    assert user.email == "Relay@privaterelay.appleid.com"


@pytest.mark.django_db
def test_apple_users_without_an_email_coexist():
    """The reason email is nullable rather than blank.

    Apple does not guarantee an email claim, so more than one user can arrive
    without one. Postgres treats NULLs as distinct, which is what lets a unique
    column hold any number of them. An empty string would collide on the second
    user and lock them out of the app permanently.
    """
    first = User.objects.create_apple_user(apple_user_id="000111.aaa.1111")
    second = User.objects.create_apple_user(apple_user_id="000222.bbb.2222")

    assert first.email is None
    assert second.email is None
    assert User.objects.filter(email__isnull=True).count() == 2


@pytest.mark.django_db
def test_apple_user_id_is_unique_at_the_database_level():
    """Application-level checks race; the constraint is what actually holds.

    Two concurrent sign-ins from one Apple account would otherwise create two
    rows and split the user's history in half.
    """
    User.objects.create_apple_user(apple_user_id="000123.abc.4567")

    with pytest.raises(IntegrityError):
        User.objects.create_apple_user(apple_user_id="000123.abc.4567")


def test_create_apple_user_requires_a_subject():
    # Guard raises before any DB access, so no django_db marker is needed.
    with pytest.raises(ValueError):
        User.objects.create_apple_user(apple_user_id="")


@pytest.mark.django_db
def test_str_falls_back_when_there_is_no_email():
    """__str__ has to work for a user who hid their email, since the admin
    changelist calls it on every row."""
    user = User.objects.create_apple_user(apple_user_id="000123.abc.4567")

    assert str(user) == "000123.abc.4567"
