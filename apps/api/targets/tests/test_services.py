"""Tests for the two-tier guardrail.

No database. These are pure functions and the tests should stay that way, so a
`django_db` mark appearing here later is a sign something leaked.

Boundaries get asserted on **both sides**, because an off-by-one in a clamp is
invisible in ordinary use and is exactly the bug a range function has. A test
that only checks the middle of a range proves the function exists.
"""

from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from targets.services import (
    ABSOLUTE_CALORIE_RANGE,
    Adjustment,
    Profile,
    Sex,
    Targets,
    absolute_calorie_range,
    clamp_to_suggested,
    reject_outside_absolute,
    suggested_calorie_range,
    suggested_fiber_range,
    suggested_protein_range,
)


def profile(sex=Sex.MALE, weight_kg="70") -> Profile:
    return Profile(sex=sex, weight_kg=Decimal(weight_kg))


def targets(calories=2150, protein_g=140, fiber_g=30) -> Targets:
    return Targets(calories=calories, protein_g=protein_g, fiber_g=fiber_g)


# --- the suggested calorie range ----------------------------------------------


def test_the_calorie_range_scales_with_body_weight():
    """The reason doc 15's fixed 1,500-3,200 was not copied. It is right for a
    mid-sized adult and wrong at both ends."""
    small = suggested_calorie_range(profile(sex=Sex.FEMALE, weight_kg="50"))
    large = suggested_calorie_range(profile(sex=Sex.MALE, weight_kg="100"))

    assert (small.floor, small.ceiling) == (1200, 2000)
    assert (large.floor, large.ceiling) == (2200, 4000)


def test_a_small_person_gets_the_sex_floor_not_the_per_kg_one():
    """22 kcal/kg is 1,100 at 50 kg, below the floor for a woman. The `max` is
    what stops the per-kg rule recommending something too low for someone
    light."""
    assert suggested_calorie_range(profile(sex=Sex.FEMALE, weight_kg="50")).floor == 1200
    assert suggested_calorie_range(profile(sex=Sex.MALE, weight_kg="50")).floor == 1500


def test_the_suggested_ceiling_never_leaves_the_absolute_range():
    """Caught while implementing, after the owner set the absolute ceiling to
    5,000. At 40 kcal/kg the per-kg ceiling passes 5,000 at about 125 kg, and
    real people weigh more than that.

    Without the clamp the app would suggest a number its own write path rejects,
    and the first person to hit it would be someone the design never pictured.
    """
    heavy = suggested_calorie_range(profile(sex=Sex.MALE, weight_kg="150"))

    assert heavy.ceiling == absolute_calorie_range().ceiling == 5000


@pytest.mark.parametrize("weight_kg", ["40", "70", "125", "126", "200"])
def test_the_suggested_range_always_nests_inside_the_absolute_one(weight_kg):
    """The invariant behind the test above, asserted across the range rather
    than at the one weight that first broke it."""
    suggested = suggested_calorie_range(profile(weight_kg=weight_kg))
    absolute = absolute_calorie_range()

    assert suggested.floor >= absolute.floor
    assert suggested.ceiling <= absolute.ceiling


# --- rounding -----------------------------------------------------------------


def test_a_fractional_floor_rounds_up_and_a_fractional_ceiling_rounds_down():
    """Both directions tighten the range, and that is deliberate.

    72.5 kg gives a floor of 1,595.0 and a ceiling of 2,900.0, so pick a weight
    that actually produces fractions: 70.7 kg is 1,555.4 and 2,828.0.

    Rounding the floor down would let a value through that the unrounded bound
    refuses. The size of that gap is silly. The direction is the point, and it is
    the kind of thing someone "simplifies" to round() while tidying up.
    """
    calories = suggested_calorie_range(profile(weight_kg="70.7"))

    assert calories.floor == 1556  # 1555.4 rounded up
    assert calories.ceiling == 2828


# --- protein and fiber --------------------------------------------------------


def test_the_protein_range_is_per_kilo_of_bodyweight():
    """1.6 to 2.5 g/kg. The best-evidenced numbers in the module."""
    band = suggested_protein_range(profile(weight_kg="80"))

    assert (band.floor, band.ceiling) == (128, 200)


def test_the_fiber_range_keys_on_calories_not_body_weight():
    """A 1,400 kcal day and a 3,000 kcal day need different fiber. Tying it to
    weight would miss that, and 14 g per 1,000 kcal is the guideline this
    brackets."""
    lean_day = suggested_fiber_range(1500)
    big_day = suggested_fiber_range(3000)

    assert (lean_day.floor, lean_day.ceiling) == (15, 30)
    assert (big_day.floor, big_day.ceiling) == (30, 60)


# --- clamping to the suggested range ------------------------------------------


def test_a_target_set_inside_the_range_is_returned_untouched():
    result = clamp_to_suggested(targets(), profile())

    assert result.targets == targets()
    assert result.adjustments == ()
    assert result.changed is False


def test_a_low_calorie_target_is_pulled_up_and_reported():
    """The case the clamp exists for. A model returning 900 kcal for a cut is not
    a bad suggestion, it is a harmful one."""
    result = clamp_to_suggested(targets(calories=900), profile())

    assert result.targets.calories == 1540
    assert result.changed is True
    assert Adjustment(field="calories", original=900, clamped=1540) in result.adjustments


def test_the_result_names_every_field_it_moved():
    """`changed` alone is not enough. MAC-41 logs which field a model got wrong,
    and doc 15's result screen shows the before and after."""
    result = clamp_to_suggested(targets(calories=900, protein_g=10, fiber_g=200), profile())

    assert {adjustment.field for adjustment in result.adjustments} == {
        "calories",
        "protein_g",
        "fiber_g",
    }


def test_fiber_is_judged_against_the_clamped_calories_not_the_requested_ones():
    """A model asking for 6,000 kcal and 90 g of fiber should be judged on the
    5,000 it actually gets.

    Against 6,000 the fiber ceiling would be 120 and 90 would pass. Against the
    clamped 5,000 it is 100, so 90 still passes, and the number that proves the
    ordering is one between the two ceilings. 110 is inside 6,000's band and
    outside 5,000's.
    """
    result = clamp_to_suggested(targets(calories=6000, fiber_g=110), profile(weight_kg="150"))

    assert result.targets.calories == 5000
    assert result.targets.fiber_g == 100


# --- the absolute range, which refuses rather than clamps ----------------------


def test_a_target_set_inside_the_absolute_range_passes_silently():
    # Not raising is the assertion. `assert ... is None` would look like a check
    # and be one, of a function annotated `-> None`. mypy caught that.
    reject_outside_absolute(targets(), profile())


@pytest.mark.parametrize("calories", [1000, 5000])
def test_the_absolute_calorie_boundary_accepts_its_own_ends(calories):
    """Inclusive on both ends. Exactly 1,000 is allowed, not one over."""
    reject_outside_absolute(targets(calories=calories), profile())


@pytest.mark.parametrize("calories", [999, 5001])
def test_one_step_outside_either_end_is_refused(calories):
    """The other half. An off-by-one in a bound is invisible in ordinary use, so
    both sides of both ends get a test."""
    with pytest.raises(ValidationError):
        reject_outside_absolute(targets(calories=calories), profile())


def test_rejecting_names_the_field_and_the_bounds():
    """The message has to say what was wrong and what would be right. "Invalid"
    sends the caller back to guess."""
    with pytest.raises(ValidationError) as raised:
        reject_outside_absolute(targets(calories=400), profile())

    message = str(raised.value.detail)
    assert "calories" in message
    assert "1000" in message
    assert "400" in message


def test_every_failing_field_is_reported_at_once():
    """Not the first one. A caller who fixes one, resubmits, and is told about
    the next has been made to guess twice."""
    with pytest.raises(ValidationError) as raised:
        reject_outside_absolute(targets(calories=400, protein_g=900, fiber_g=500), profile())

    assert set(raised.value.detail) == {"calories", "protein_g", "fiber_g"}


def test_a_zero_fiber_target_is_allowed():
    """A user may not want a fiber target, and refusing that would be the app
    having an opinion where it has no standing."""
    reject_outside_absolute(targets(fiber_g=0), profile())


def test_the_absolute_protein_range_scales_with_weight():
    """0.5 to 3.5 g/kg. Wide enough that anything outside is a mistyped number
    rather than a preference."""
    light = profile(weight_kg="50")

    reject_outside_absolute(targets(protein_g=25), light)
    with pytest.raises(ValidationError):
        reject_outside_absolute(targets(protein_g=24), light)


# --- the two tiers do different things ----------------------------------------


def test_a_value_outside_suggested_but_inside_absolute_is_clamped_yet_accepted():
    """The whole point of two tiers, in one test.

    1,200 kcal for a 70 kg man is below the suggested floor of 1,540 and above
    the absolute floor of 1,000. The AI path pulls it up. The manual path stores
    it as typed, because a person is allowed to disagree with the app about their
    own body.
    """
    low = targets(calories=1200)
    person = profile()

    assert clamp_to_suggested(low, person).targets.calories == 1540
    reject_outside_absolute(low, person)


def test_the_constants_are_a_module_level_pair_not_settings():
    """Both ranges live in code so a change moves through a pull request where
    someone reads the diff. An env override would also split the tested value
    from the live one, which is the failure MAC-36 spent two PRs closing."""
    assert ABSOLUTE_CALORIE_RANGE == (1000, 5000)
