"""Tests for `services.create_version`, the one door that makes a TargetVersion.

Separate from `test_services.py`, which is pure arithmetic and says so in its
own docstring. These need the database, because what they check is two rows
moving together.
"""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from targets import services
from targets.models import TargetVersion


def test_create_version_updates_the_user_object_it_was_given(db):
    """The in-memory user matches the row after the call, not just the database.

    `.update()` writes SQL and goes round the Python object, so `user` would
    still say False while the row says True. Nothing later in a request reads
    the flag today. Two objects disagreeing is how that stops being true without
    anyone noticing, and the endpoint tests cannot see it because the request
    builds its own user.
    """
    user = get_user_model().objects.create_user(email="fresh@example.com")

    services.create_version(
        user=user,
        calories=2150,
        protein_g=140,
        fiber_g=30,
        source=TargetVersion.Source.MANUAL,
        effective_from=timezone.now().date(),
    )

    assert user.onboarding_completed is True


def test_create_version_rolls_the_flag_back_with_the_row(db):
    """One transaction, proved by breaking the second write.

    A target that saves while the flag write fails leaves a user who owns
    targets and is still sent to onboarding on every launch. That is the bug
    MAC-47 fixes, so shipping a version of it inside the fix would be a poor
    joke.
    """
    user = get_user_model().objects.create_user(email="rollback@example.com")

    with mock.patch.object(services, "get_user_model", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            services.create_version(
                user=user,
                calories=2150,
                protein_g=140,
                fiber_g=30,
                source=TargetVersion.Source.MANUAL,
                effective_from=timezone.now().date(),
            )

    user.refresh_from_db()
    assert user.onboarding_completed is False
    assert TargetVersion.objects.filter(user=user).count() == 0


def test_the_flag_update_carries_its_condition_in_the_where_clause(db):
    """The conditional UPDATE, pinned on the SQL, because nothing else can see it.

    The endpoint test asserting the flag is still True after a second target
    passes either way: writing True over True is invisible from outside. That
    let the mutation "drop `onboarding_completed=False` from the filter"
    survive, which means the design this function documents at length was
    unproven.

    White-box, and deliberately so. What the condition buys is that **the
    database decides who is first**, not Python. Two requests racing on a user's
    first target cannot both win, because only one UPDATE matches the row. Move
    the check into an `if` in Python and both read False, both write, and the
    guarantee is gone with every test still green.

    The query still runs on a later target. It simply matches no rows.
    """
    user = get_user_model().objects.create_user(email="second@example.com")

    with CaptureQueriesContext(connection) as captured:
        services.create_version(
            user=user,
            calories=2150,
            protein_g=140,
            fiber_g=30,
            source=TargetVersion.Source.MANUAL,
            effective_from=timezone.now().date(),
        )

    updates = [q["sql"] for q in captured.captured_queries if q["sql"].startswith("UPDATE")]
    assert len(updates) == 1
    assert "onboarding_completed" in updates[0]
    # The guard itself. Without it the statement is an unconditional write.
    assert "NOT" in updates[0]
