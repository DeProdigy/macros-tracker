"""Tests for TargetVersion.

Two properties carry the weight here, and both are easy to break without
noticing.

The first is that `current()` is *deterministic*. "Latest by created_at" picks
arbitrarily between rows sharing a timestamp. That collision does not happen by
accident here -- `auto_now_add` reads Python's clock per row, so ordinary saves
land microseconds apart -- which is precisely why the test has to force it. An
untested tiebreak is one someone deletes as noise.

The second is that a new version leaves every older row untouched. That is the
entire promise of the append-only model, and nothing in the schema enforces it --
only the absence of code that updates in place.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from targets.models import TargetVersion

User = get_user_model()

TODAY = timezone.now().date()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alex@example.com")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="someone-else@example.com")


def make_version(user, *, calories=2150, source=TargetVersion.Source.MANUAL, **extra):
    defaults = {
        "protein_g": 176,
        "fiber_g": 32,
        "effective_from": TODAY,
        **extra,
    }
    return TargetVersion.objects.create(user=user, calories=calories, source=source, **defaults)


# --- current() ----------------------------------------------------------------


@pytest.mark.django_db
def test_current_is_none_before_any_targets_exist(user):
    """A user with no targets is a supported state, not an error. They logged a
    meal and skipped onboarding, which doc 26 designed as a real exit."""
    assert TargetVersion.objects.current(user) is None


@pytest.mark.django_db
def test_current_is_the_only_version_when_there_is_one(user):
    version = make_version(user)

    assert TargetVersion.objects.current(user) == version


@pytest.mark.django_db
def test_current_is_the_newest_of_several(user):
    make_version(user, calories=2000)
    make_version(user, calories=2100)
    newest = make_version(user, calories=2200)

    assert TargetVersion.objects.current(user) == newest


@pytest.mark.django_db
def test_current_is_deterministic_when_timestamps_collide(user):
    """The reason `-id` is in Meta.ordering.

    The collision has to be forced. `auto_now_add` reads Python's clock at save
    time, so ordinary creates land microseconds apart and never exercise this --
    which is exactly why the tiebreak would otherwise look untested and get
    deleted as noise by someone tidying up. Equal timestamps are reachable
    through `bulk_create`, a data migration, or a fixture that sets the column,
    and `.update()` is the cheapest way to reproduce that here.

    With `-created_at` alone the database is free to return either row, so
    `current()` could flip between two different calorie targets across
    identical requests.
    """
    older = make_version(user, calories=2000)
    newer = make_version(user, calories=2200)

    # Bypasses auto_now_add, which ignores assignment on save().
    collision = older.created_at
    TargetVersion.objects.filter(pk=newer.pk).update(created_at=collision)

    current = TargetVersion.objects.current(user)
    assert current is not None
    assert current.pk == newer.pk


@pytest.mark.django_db
def test_current_ignores_another_users_versions(user, other_user):
    """Cross-user isolation gets its own test rather than being assumed. This
    queryset has no permission layer above it -- MAC-40's views do -- so the
    scoping has to be right here."""
    make_version(other_user, calories=3000)

    assert TargetVersion.objects.current(user) is None

    theirs = TargetVersion.objects.current(other_user)
    assert theirs is not None
    assert theirs.calories == 3000


# --- append-only --------------------------------------------------------------


@pytest.mark.django_db
def test_a_new_version_leaves_the_previous_one_untouched(user):
    """The promise the whole model exists for. Nothing in the schema enforces
    it, so it is worth asserting rather than assuming."""
    first = make_version(user, calories=2000, protein_g=150, fiber_g=30)

    make_version(user, calories=2200, protein_g=180, fiber_g=35)

    first.refresh_from_db()
    assert (first.calories, first.protein_g, first.fiber_g) == (2000, 150, 30)
    assert TargetVersion.objects.for_user(user).count() == 2


@pytest.mark.django_db
def test_versions_list_newest_first(user):
    """What the history screen (doc 16, 7d) and `GET /api/targets/` both read."""
    oldest = make_version(user, calories=2000)
    middle = make_version(user, calories=2100)
    newest = make_version(user, calories=2200)

    assert list(TargetVersion.objects.for_user(user)) == [newest, middle, oldest]


# --- fields -------------------------------------------------------------------


@pytest.mark.django_db
def test_a_manual_version_stores_an_empty_rationale_not_null(user):
    """`ai_rationale` is `blank=True`, never nullable. A nullable text field
    gives two ways to spell "empty" and every reader has to handle both."""
    version = make_version(user, source=TargetVersion.Source.MANUAL)

    assert version.ai_rationale == ""


@pytest.mark.django_db
def test_an_onboarding_version_keeps_its_rationale(user):
    version = make_version(
        user,
        source=TargetVersion.Source.ONBOARDING_AI,
        ai_rationale="A 400 kcal deficit puts you on track for roughly 0.4 kg a week.",
    )

    version.refresh_from_db()
    assert version.source == "onboarding_ai"
    assert version.ai_rationale.startswith("A 400 kcal deficit")


@pytest.mark.django_db
def test_effective_from_has_no_default_and_must_be_supplied(user):
    """Deliberate, and the reason is a timezone bug that would otherwise hide in
    a column. `User.timezone` is "UTC" for everyone until MAC-48 ships, so a
    server-side `timezone.now().date()` default would hand a caller in Los
    Angeles tomorrow's date at 5pm. The client sends its own calendar date, the
    same way doc 02's write path does for DailyLog.
    """
    from django.db.utils import IntegrityError

    with pytest.raises(IntegrityError):
        TargetVersion.objects.create(
            user=user,
            calories=2150,
            protein_g=176,
            fiber_g=32,
            source=TargetVersion.Source.MANUAL,
        )
