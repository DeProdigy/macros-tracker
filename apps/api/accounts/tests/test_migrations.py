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

from decimal import Decimal

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


# --- 0006, the kilograms-to-pounds conversion -------------------------------
#
# The same argument this file already makes for 0003. Review pointed out that
# the conversion this PR called its risky part was the one piece with no test:
# swapping the `*` for a `/`, or deleting the RunPython line outright, left all
# 322 tests passing.

BEFORE_POUNDS = [("accounts", "0005_user_settings_fields")]
AFTER_POUNDS = [("accounts", "0006_pounds_and_onboarding_answers")]


@pytest.mark.django_db(transaction=True)
def test_0006_converts_a_stored_goal_weight_to_pounds():
    """80 kg is 176.37 lb, and the row has to come out the other side holding it.

    A rename alone would leave 80.00 sitting in a column now labelled pounds,
    which is the silent version of this bug: no error, no missing row, just a
    number that means something different than it says.
    """
    old_apps = _migrate(BEFORE_POUNDS)
    User = old_apps.get_model("accounts", "User")
    User.objects.create(email="goal@example.com", goal_weight_kg=Decimal("80.00"))

    new_apps = _migrate(AFTER_POUNDS)
    user = new_apps.get_model("accounts", "User").objects.get(email="goal@example.com")

    assert user.goal_weight_lb == Decimal("176.37")


@pytest.mark.django_db(transaction=True)
def test_0006_reverses_back_to_kilograms():
    """The reverse is a real inverse, not a `noop`.

    A migration that cannot go back is one you find out about while trying to go
    back, which is the worst moment to find out.
    """
    old_apps = _migrate(BEFORE_POUNDS)
    old_apps.get_model("accounts", "User").objects.create(
        email="reverse@example.com", goal_weight_kg=Decimal("80.00")
    )
    _migrate(AFTER_POUNDS)

    back = _migrate(BEFORE_POUNDS)
    user = back.get_model("accounts", "User").objects.get(email="reverse@example.com")

    assert user.goal_weight_kg == Decimal("80.00")


@pytest.mark.django_db(transaction=True)
def test_0006_leaves_an_unanswered_goal_weight_null():
    """Most users never answer this. `exclude(goal_weight_lb=None)` is what keeps
    the conversion off them, and multiplying a null would raise rather than skip."""
    old_apps = _migrate(BEFORE_POUNDS)
    old_apps.get_model("accounts", "User").objects.create(email="null@example.com")

    new_apps = _migrate(AFTER_POUNDS)
    user = new_apps.get_model("accounts", "User").objects.get(email="null@example.com")

    assert user.goal_weight_lb is None


@pytest.mark.django_db(transaction=True)
def test_0006_refuses_a_goal_weight_that_would_convert_out_of_bounds():
    """The gap between the old bounds and the new ones, guarded.

    The old column allowed 20 to 400 kg. The new one allows 85 to 500 lb, which
    is 38.56 to 226.80 kg, so the two do not nest. 30 kg converts to 66.14 lb,
    below the new floor.

    Left alone the migration writes it anyway, because validators do not run on a
    `RunPython` save. The row would exist and be unsavable through PATCH or the
    admin, which is the failure this migration was hand-written to avoid.

    It raises rather than clamping. Clamping silently changes a number a person
    entered; raising makes a deploy stop and someone look.
    """
    old_apps = _migrate(BEFORE_POUNDS)
    old_apps.get_model("accounts", "User").objects.create(
        email="tiny@example.com", goal_weight_kg=Decimal("30.00")
    )

    try:
        with pytest.raises(RuntimeError, match="outside the new"):
            _migrate(AFTER_POUNDS)
    finally:
        # The expected exception leaves the shared test schema at 0005. Restore
        # it just like the `at_0002` fixture does above, or every transactional
        # test collected after this file sees current model code against an old
        # database schema. Remove the deliberately invalid row first so the
        # migration can complete on the second attempt.
        old_apps.get_model("accounts", "User").objects.filter(email="tiny@example.com").delete()
        _migrate(AFTER_POUNDS)
