"""Tests for `services.create_version`, the one door that makes a TargetVersion.

Separate from `test_services.py`, which is pure arithmetic and says so in its
own docstring. These need the database, because what they check is two rows
moving together.
"""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
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


def test_complete_onboarding_reports_whether_it_was_the_one_that_flipped(db):
    """The conditional UPDATE, pinned on behaviour rather than on generated SQL.

    The endpoint test asserting the flag is still True after a second target
    passes either way: writing True over True is invisible from outside. That
    let the mutation "drop `onboarding_completed=False` from the filter"
    survive, which means the design was documented at length and proved by
    nothing.

    The first fix for that read the SQL out of `CaptureQueriesContext` and
    asserted `"NOT" in`, which is a substring check standing in for a semantic
    one and would match a `NOT` in any clause or column name. Review pointed out
    that `.update()` already returns the row count, so the answer was sitting
    inside the function the whole time. It just needed a name and a return value.

    Drop the condition from the filter and the second call returns True, because
    an unconditional UPDATE matches the row every time.
    """
    user = get_user_model().objects.create_user(email="second@example.com")

    assert services.complete_onboarding(user) is True
    assert services.complete_onboarding(user) is False
