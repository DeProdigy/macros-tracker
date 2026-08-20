"""Tests for the 0003 data migration.

Migrations are code that runs exactly once per database and then never again,
which makes them the easiest code in the project to ship broken. This one is
also the only place that knows `User.apple_user_id` and `Identity.subject` mean
the same thing -- the autodetector cannot infer that, so nothing but this file
carries the knowledge.

Driven through Django's own MigrationExecutor rather than a helper library, so
the models really are the historical ones: `apple_user_id` exists at 0002 and is
gone at 0003, which is exactly what makes the assertion meaningful.

`transaction=True` because the executor issues DDL. Inside pytest-django's usual
wrapping transaction the schema changes would be invisible to the connection
doing the querying.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("accounts", "0002_remove_user_is_email_verified_alter_user_email")]
AFTER = [("accounts", "0003_identity_join_table")]

APPLE_SUB = "000123.migrated.4567"


def _migrate(targets):
    """Run to `targets` and hand back the model registry as of that point."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


@pytest.fixture
def at_0002():
    """Rewind to before the split, and always roll forward again afterwards.

    The teardown matters more than the setup. A failure mid-test would
    otherwise leave the test database on an older schema, and every later test
    in the session would fail with a confusing error about a missing table
    rather than pointing at this file.
    """
    old_apps = _migrate(BEFORE)
    yield old_apps
    _migrate(AFTER)


@pytest.mark.django_db(transaction=True)
def test_forward_copies_the_subject_onto_an_identity(at_0002):
    User = at_0002.get_model("accounts", "User")
    User.objects.create(
        email="migrated@example.com",
        apple_user_id=APPLE_SUB,
        password="!unusable",
        is_active=True,
        is_staff=False,
        is_superuser=False,
        timezone="UTC",
        onboarding_completed=False,
        ai_calls_this_month=0,
    )

    new_apps = _migrate(AFTER)

    Identity = new_apps.get_model("accounts", "Identity")
    identity = Identity.objects.get(subject=APPLE_SUB)
    assert identity.provider == "apple"
    assert identity.user.email == "migrated@example.com"


@pytest.mark.django_db(transaction=True)
def test_a_user_without_a_subject_gets_no_identity(at_0002):
    """A superuser has a password and no Apple credential.

    `exclude(apple_user_id=None)` is what keeps the migration from inventing an
    identity with a NULL subject for them, which the constraint would then have
    opinions about.
    """
    User = at_0002.get_model("accounts", "User")
    User.objects.create(
        email="staff@example.com",
        apple_user_id=None,
        password="argon2$fake",
        is_active=True,
        is_staff=True,
        is_superuser=True,
        timezone="UTC",
        onboarding_completed=False,
        ai_calls_this_month=0,
    )

    new_apps = _migrate(AFTER)

    Identity = new_apps.get_model("accounts", "Identity")
    assert not Identity.objects.filter(user__email="staff@example.com").exists()


@pytest.mark.django_db(transaction=True)
def test_the_migration_round_trips(at_0002):
    """Reverse then forward, with the subject surviving both directions.

    Production is empty, so a reversible RunPython was optional here. Writing it
    is cheap insurance for local databases, and the only honest way to know a
    rollback works is to run one.
    """
    User = at_0002.get_model("accounts", "User")
    User.objects.create(
        email="roundtrip@example.com",
        apple_user_id=APPLE_SUB,
        password="!unusable",
        is_active=True,
        is_staff=False,
        is_superuser=False,
        timezone="UTC",
        onboarding_completed=False,
        ai_calls_this_month=0,
    )

    _migrate(AFTER)
    back_apps = _migrate(BEFORE)

    OldUser = back_apps.get_model("accounts", "User")
    assert OldUser.objects.get(email="roundtrip@example.com").apple_user_id == APPLE_SUB

    forward_apps = _migrate(AFTER)
    Identity = forward_apps.get_model("accounts", "Identity")
    assert Identity.objects.filter(subject=APPLE_SUB).count() == 1
