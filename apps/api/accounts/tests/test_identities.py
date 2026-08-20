"""Tests for the Identity table and the sign-in stamps.

The assertions that matter here are the structural ones. A join table that
happens to work for one provider proves nothing about why it exists, so these
exercise the cases that only appear with two: a subject shared across providers,
several identities on one user, a cascade that removes credentials without
touching the person.

The atomicity test is the one worth reading. Two rows that must both land or
neither is the whole argument for `transaction.atomic` here, and the failure it
prevents is silent: a user with no identity can never sign in, and does not
block the retry either, so the next attempt forks a second account.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts import services
from accounts.models import Identity

User = get_user_model()

APPLE_SUB = "000123.abcdef.4567"


def claims(**overrides) -> services.AppleClaims:
    defaults = {
        "subject": APPLE_SUB,
        "email": "user@example.com",
        "is_private_email": False,
        "real_user_status": Identity.RealUserStatus.LIKELY_REAL,
    }
    return services.AppleClaims(**{**defaults, **overrides})


# --- creation ---------------------------------------------------------------


@pytest.mark.django_db
def test_create_apple_user_writes_both_rows():
    user = User.objects.create_apple_user(
        apple_user_id=APPLE_SUB,
        email="user@example.com",
        is_private_email=True,
        real_user_status=Identity.RealUserStatus.LIKELY_REAL,
    )

    identity = user.identities.get()
    assert identity.provider == Identity.Provider.APPLE
    assert identity.subject == APPLE_SUB
    assert identity.is_private_email is True
    assert identity.real_user_status == Identity.RealUserStatus.LIKELY_REAL
    assert identity.last_authenticated_at is None


@pytest.mark.django_db
def test_create_apple_user_writes_neither_row_when_the_identity_fails():
    """The reason create_apple_user is wrapped in transaction.atomic.

    Without it, a failure between the two writes leaves a user row with no
    identity. That user can never sign in, and their row does not block the
    retry either, so the next attempt creates a second account for one person.
    Both halves of that are silent.

    Driven by a real constraint violation rather than a mock. The natural way to
    reach this is two concurrent sign-ins from the same Apple account: the user
    INSERT succeeds, the identity INSERT loses the race, and the whole thing has
    to unwind. Mocking the failure would have tested the mock -- an earlier
    attempt patched `Identity.objects.create` and never fired at all, because
    the manager call goes through `.using()` and returns a different queryset.
    """
    User.objects.create_apple_user(apple_user_id=APPLE_SUB)
    before = User.objects.count()

    # atomic() because the failed INSERT poisons the surrounding test
    # transaction; without a savepoint nothing after this can query.
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_apple_user(apple_user_id=APPLE_SUB, email="second@example.com")

    assert User.objects.count() == before
    assert Identity.objects.count() == 1
    assert not User.objects.filter(email="second@example.com").exists()


@pytest.mark.django_db
def test_unset_apple_claims_store_as_null_not_false():
    """None and False are different answers about a relay address.

    Defaulting is_private_email to False would assert a deliverable address
    Apple never told us about.
    """
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)

    identity = user.identities.get()
    assert identity.is_private_email is None
    assert identity.real_user_status is None


# --- the constraint ---------------------------------------------------------


@pytest.mark.django_db
def test_two_providers_may_share_a_subject():
    """Why the constraint is on the pair and not on subject alone.

    Providers mint opaque strings from their own namespaces and nothing
    coordinates them. A unique index on subject by itself would be a
    cross-provider collision that fires once, years later, unreproducibly.
    """
    alice = User.objects.create_apple_user(apple_user_id=APPLE_SUB)
    bob = User.objects.create_user(email="bob@example.com", password="pw-not-real-12345")

    Identity.objects.create(user=bob, provider="google", subject=APPLE_SUB)

    assert Identity.objects.filter(subject=APPLE_SUB).count() == 2
    assert alice.identities.count() == 1


@pytest.mark.django_db
def test_the_same_pair_cannot_be_registered_twice():
    """Application-level checks race; the constraint is what actually holds.

    Two concurrent sign-ins from one Apple account would otherwise create two
    users and split one person's history in half.
    """
    User.objects.create_apple_user(apple_user_id=APPLE_SUB)

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_apple_user(apple_user_id=APPLE_SUB)


@pytest.mark.django_db
def test_one_user_can_hold_several_identities():
    """The relation this refactor exists for, asserted rather than assumed."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)
    Identity.objects.create(user=user, provider="google", subject="google-999")

    assert user.identities.count() == 2


# --- deletion ---------------------------------------------------------------


@pytest.mark.django_db
def test_hard_delete_removes_identities():
    """CASCADE only fires on MAC-29's purge, which is when it should."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)

    user.delete()

    assert Identity.objects.count() == 0


@pytest.mark.django_db
def test_soft_delete_leaves_identities_alone():
    """Soft delete is a property of the person, not of a credential.

    MAC-27 reactivates a user inside the grace window by clearing deleted_at,
    which only works if their identity survived.
    """
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)

    user.deleted_at = timezone.now()
    user.is_active = False
    user.save(update_fields=["deleted_at", "is_active"])

    assert user.identities.count() == 1


# --- record_authentication --------------------------------------------------


@pytest.mark.django_db
def test_record_authentication_stamps_both_sides():
    """The last_login fix. Nothing wrote it before, and the admin displayed it
    anyway, so every active user read as 'never logged in'."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)
    identity = user.identities.get()
    assert user.last_login is None

    services.record_authentication(identity, claims=claims())

    identity.refresh_from_db()
    user.refresh_from_db()
    assert identity.last_authenticated_at is not None
    assert user.last_login is not None


@pytest.mark.django_db
def test_second_sign_in_refreshes_is_private_email():
    """Current state, so it tracks a user switching to or from a relay."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB, is_private_email=False)
    identity = user.identities.get()

    services.record_authentication(identity, claims=claims(is_private_email=True))

    identity.refresh_from_db()
    assert identity.is_private_email is True


@pytest.mark.django_db
def test_absent_is_private_email_does_not_clear_the_stored_value():
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB, is_private_email=True)
    identity = user.identities.get()

    services.record_authentication(identity, claims=claims(is_private_email=None))

    identity.refresh_from_db()
    assert identity.is_private_email is True


@pytest.mark.django_db
def test_real_user_status_is_never_overwritten():
    """Apple sends it on the first authorization only.

    A later token carries None, and if one ever carried UNKNOWN, writing it
    would silently downgrade a stored LIKELY_REAL. The field records what Apple
    thought when the identity was first seen, which is a fact about one moment.
    """
    user = User.objects.create_apple_user(
        apple_user_id=APPLE_SUB,
        real_user_status=Identity.RealUserStatus.LIKELY_REAL,
    )
    identity = user.identities.get()

    services.record_authentication(
        identity, claims=claims(real_user_status=Identity.RealUserStatus.UNKNOWN)
    )

    identity.refresh_from_db()
    assert identity.real_user_status == Identity.RealUserStatus.LIKELY_REAL


@pytest.mark.django_db
def test_repeated_sign_ins_move_the_timestamp_forward():
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)
    identity = user.identities.get()

    services.record_authentication(identity, claims=claims())
    identity.refresh_from_db()
    first = identity.last_authenticated_at
    assert first is not None

    Identity.objects.filter(pk=identity.pk).update(last_authenticated_at=first - timedelta(days=1))
    identity.refresh_from_db()

    services.record_authentication(identity, claims=claims())
    identity.refresh_from_db()
    assert identity.last_authenticated_at > first - timedelta(days=1)
