"""Tests for the custom User model and its manager.

RSpec equivalent: `spec/models/user_spec.rb`. These pin down the behaviour of
`UserManager.create_user` / `create_superuser`.

`@pytest.mark.django_db` grants a test access to the (rolled-back) test database
— the equivalent of RSpec's transactional fixtures. Tests without it must not
touch the DB, which is why the pure-guard cases below omit it.
"""

import pytest
from django.contrib.auth import get_user_model

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
    assert not user.is_email_verified
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
