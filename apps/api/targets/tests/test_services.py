"""Tests for the two-tier guardrail.

No database. These are pure functions and the tests should stay that way, so a
`django_db` mark appearing here later is a sign something leaked.

Weights are in **pounds**, like the rest of the stack. The evidence behind the
ratios is published per kilogram, so a few expected values look untidy. That is
the conversion showing through, and rounding the constants to tidy them would
quietly move numbers taken from research.

Boundaries get asserted on **both sides**, because an off-by-one in a clamp is
invisible in ordinary use and is exactly the bug a range function has. A test
that only checks the middle of a range proves the function exists.
"""

from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from targets.services import (
    ABSOLUTE_CALORIE_RANGE,
    MINIMUM_SUPPORTED_WEIGHT_LB,
    Adjustment,
    Profile,
    Range,
    Sex,
    Targets,
    absolute_calorie_range,
    absolute_fiber_range,
    clamp_to_suggested,
    reject_outside_absolute,
    suggested_calorie_range,
    suggested_fiber_range,
    suggested_protein_range,
)

# Real body weights in pounds. 155 lb is the mid-sized adult doc 15's fixed
# range was written around.
LIGHT_LB = "110"
MID_LB = "155"
HEAVY_LB = "220"


def profile(sex=Sex.MALE, weight_lb=MID_LB) -> Profile:
    return Profile(sex=sex, weight_lb=Decimal(weight_lb))


def targets(calories=2150, protein_g=140, fiber_g=30) -> Targets:
    return Targets(calories=calories, protein_g=protein_g, fiber_g=fiber_g)


# --- Range guards itself ------------------------------------------------------


def test_a_crossed_range_raises_rather_than_failing_quietly():
    """The guard exists because an inverted range is silently wrong in both
    directions.

    `clamp` becomes `max(floor, min(ceiling, value))`, which returns the floor
    for every input and ignores the ceiling. `contains` returns False for every
    input. Nothing raises, nothing logs, and the numbers are just wrong.

    Same reasoning that named the two fields instead of using a tuple. A swapped
    pair passes every type check; so does a crossed one.
    """
    with pytest.raises(ValueError, match="above ceiling"):
        Range(floor=1500, ceiling=1400)


def test_a_single_value_range_is_allowed():
    """Floor equal to ceiling is degenerate but not wrong, and `>` rather than
    `>=` is what keeps it legal."""
    assert Range(floor=2000, ceiling=2000).contains(2000)


# --- the suggested calorie range ----------------------------------------------


def test_the_calorie_range_scales_with_body_weight():
    """The reason doc 15's fixed 1,500-3,200 was not copied. It is right for a
    mid-sized adult and wrong at both ends."""
    small = suggested_calorie_range(profile(sex=Sex.FEMALE, weight_lb=LIGHT_LB))
    large = suggested_calorie_range(profile(sex=Sex.MALE, weight_lb=HEAVY_LB))

    assert (small.floor, small.ceiling) == (1200, 1995)
    assert (large.floor, large.ceiling) == (2196, 3991)


def test_a_small_person_gets_the_sex_floor_not_the_per_pound_one():
    """The per-pound rule gives 1,098 at 110 lb, below the floor for a woman. The
    `max` is what stops it recommending something too low for someone light."""
    assert suggested_calorie_range(profile(sex=Sex.FEMALE, weight_lb=LIGHT_LB)).floor == 1200
    assert suggested_calorie_range(profile(sex=Sex.MALE, weight_lb=LIGHT_LB)).floor == 1500


def test_the_suggested_ceiling_never_leaves_the_absolute_range():
    """The per-pound ceiling passes 5,000 at about 276 lb, and people weigh more
    than that.

    Without the `min` the app would suggest a number its own write path rejects,
    and the first person to hit it would be someone the design never pictured.
    """
    heavy = suggested_calorie_range(profile(weight_lb="330"))

    assert heavy.ceiling == absolute_calorie_range().ceiling == 5000


@pytest.mark.parametrize("weight_lb", ["85", "110", "155", "275", "276", "440"])
def test_the_suggested_range_always_nests_inside_the_absolute_one(weight_lb):
    """Across the supported band rather than at the one weight that first broke
    it, and starting at the documented minimum rather than comfortably above."""
    suggested = suggested_calorie_range(profile(weight_lb=weight_lb))
    absolute = absolute_calorie_range()

    assert suggested.floor >= absolute.floor
    assert suggested.ceiling <= absolute.ceiling


@pytest.mark.parametrize("weight_lb", ["85", "110", "155", "275", "276", "440"])
@pytest.mark.parametrize("sex", [Sex.FEMALE, Sex.MALE])
def test_no_supported_weight_produces_a_crossed_range(weight_lb, sex):
    """The invariant the nesting test does not catch.

    Nesting still holds when a range inverts, so a passing nesting test says
    nothing about floor against ceiling. This is the one that would have caught
    the low-weight bug, and it runs against both sexes because the male floor is
    higher and inverts first.
    """
    person = profile(sex=sex, weight_lb=weight_lb)

    for band in (
        suggested_calorie_range(person),
        suggested_protein_range(person),
        suggested_fiber_range(suggested_calorie_range(person).floor),
    ):
        assert band.floor <= band.ceiling


def test_a_weight_below_the_supported_minimum_raises():
    """A precondition, stated in `Profile` and enforced by MAC-40. The `Range`
    guard is the backstop, and it raises rather than repairing: widening the
    ceiling to meet the floor would invent a recommendation for a body these
    numbers were never derived for.

    The realistic trigger is a typo. 70 instead of 170.
    """
    with pytest.raises(ValueError, match="above ceiling"):
        suggested_calorie_range(profile(sex=Sex.MALE, weight_lb="70"))


def test_the_documented_minimum_clears_both_sexes():
    """85 lb is above the male crossing at ~83 and the female one at ~66, so the
    constant is not a guess that happens to work for one of them."""
    for sex in (Sex.FEMALE, Sex.MALE):
        band = suggested_calorie_range(profile(sex=sex, weight_lb=str(MINIMUM_SUPPORTED_WEIGHT_LB)))
        assert band.floor <= band.ceiling


# --- rounding -----------------------------------------------------------------


def test_a_fractional_floor_rounds_up_and_a_fractional_ceiling_rounds_down():
    """Both directions tighten the range, and that is deliberate.

    155 lb gives a floor of 1,546.75 and a ceiling of 2,812.27.

    Rounding the floor down would let a value through that the unrounded bound
    refuses. The size of that gap is silly. The direction is the point, and it is
    the kind of thing someone "simplifies" to round() while tidying up.
    """
    calories = suggested_calorie_range(profile(weight_lb=MID_LB))

    assert calories.floor == 1547  # 1546.75 rounded up
    assert calories.ceiling == 2812  # 2812.27 rounded down


# --- protein and fiber --------------------------------------------------------


def test_the_protein_range_is_per_pound_of_bodyweight():
    """1.6 to 2.5 g/kg, the best-evidenced numbers in the module, expressed per
    pound. 220 lb is 159.7 to 249.5 g."""
    band = suggested_protein_range(profile(weight_lb=HEAVY_LB))

    assert (band.floor, band.ceiling) == (160, 249)


def test_the_fiber_range_keys_on_calories_not_body_weight():
    """A 1,500 kcal day and a 3,000 kcal day need different fiber. Tying it to
    weight would miss that, and 14 g per 1,000 kcal is the guideline this
    brackets."""
    lean_day = suggested_fiber_range(1500)
    big_day = suggested_fiber_range(3000)

    assert (lean_day.floor, lean_day.ceiling) == (15, 30)
    assert (big_day.floor, big_day.ceiling) == (30, 60)


def test_the_suggested_fiber_range_nests_inside_the_absolute_one():
    """Caught in review. This function is public, so a caller can hand it an
    unclamped number.

    At 6,000 kcal the per-1,000 rule gives a ceiling of 120 and the write path
    refuses anything over 100. Inside `clamp_to_suggested` the calorie clamp runs
    first and hides it. Relying on call order to keep a public function honest is
    how the order eventually gets changed by someone who does not know it was
    load-bearing.
    """
    assert suggested_fiber_range(6000).ceiling == absolute_fiber_range().ceiling == 100


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

    assert result.targets.calories == 1547
    assert result.changed is True
    assert Adjustment(field="calories", original=900, clamped=1547) in result.adjustments


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
    """A model asking for 6,000 kcal is judged on the 5,000 it actually gets.

    Both ceilings now cap at 100 because of the absolute nesting, so the number
    that proves the ordering is one between the two *floors*: 6,000 asks for at
    least 60 g, and 5,000 for at least 50. A 55 g request survives against the
    clamped calories and would have been pulled up against the requested ones.
    """
    result = clamp_to_suggested(targets(calories=6000, fiber_g=55), profile(weight_lb="330"))

    assert result.targets.calories == 5000
    assert result.targets.fiber_g == 55


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
    """0.5 to 3.5 g/kg, per pound. At 110 lb that is 25 to 174 g, wide enough
    that anything outside is a mistyped number rather than a preference."""
    light = profile(weight_lb=LIGHT_LB)

    reject_outside_absolute(targets(protein_g=25), light)
    with pytest.raises(ValidationError):
        reject_outside_absolute(targets(protein_g=24), light)


# --- the two tiers do different things ----------------------------------------


def test_a_value_outside_suggested_but_inside_absolute_is_clamped_yet_accepted():
    """The whole point of two tiers, in one test.

    1,200 kcal for a 155 lb man is below the suggested floor of 1,547 and above
    the absolute floor of 1,000. The AI path pulls it up. The manual path stores
    it as typed, because a person is allowed to disagree with the app about their
    own body.
    """
    low = targets(calories=1200)
    person = profile()

    assert clamp_to_suggested(low, person).targets.calories == 1547
    reject_outside_absolute(low, person)


def test_the_constants_are_a_module_level_pair_not_settings():
    """Both ranges live in code so a change moves through a pull request where
    someone reads the diff. An env override would also split the tested value
    from the live one, which is the failure MAC-36 spent two PRs closing."""
    assert ABSOLUTE_CALORIE_RANGE == (1000, 5000)
