"""Tests for the deterministic proposal: the formula, the guardrails, the prose.

No database. This is the same pure-function module `test_services.py` covers,
split out because the subject is different: that file tests the bounds, this one
tests the arithmetic held inside them.

**The worked examples below are checked by hand against the published
Mifflin-St Jeor equation**, not against what the code happens to return. A test
that records current behaviour cannot tell you the behaviour is wrong.
"""

from decimal import Decimal

import pytest

from targets.services import (
    ABSOLUTE_CALORIE_RANGE,
    MAXIMUM_SUPPORTED_WEIGHT_LB,
    MINIMUM_SUPPORTED_WEIGHT_LB,
    Activity,
    Answers,
    Goal,
    Sex,
    Targets,
    absolute_fiber_range,
    absolute_protein_range,
    basal_metabolic_rate,
    baseline_targets,
    explain,
    maintenance_calories,
    propose,
    suggested_calorie_range,
    suggested_fiber_range,
    suggested_protein_range,
)


def answers(
    *,
    age: int = 35,
    sex: Sex = Sex.MALE,
    height_in: int = 71,
    weight_lb: Decimal = Decimal("155"),
    goal: Goal = Goal.CUT,
    activity: Activity = Activity.MODERATE,
) -> Answers:
    """A 35 year old man, 5'11", 155 lb, cutting on moderate activity.

    Spelled out rather than `**overrides`, so mypy checks a wrong type at the
    call site instead of inside the dataclass.
    """
    return Answers(
        age=age,
        sex=sex,
        height_in=height_in,
        weight_lb=weight_lb,
        goal=goal,
        activity=activity,
    )


# --- the formula, worked by hand ---------------------------------------------


def test_mifflin_for_a_man():
    """155 lb, 5'11", 35.

        70.3068 kg * 10   = 703.07
        180.34 cm * 6.25  = 1127.13
        35 * 5            = -175
        male constant     = +5
                          = 1660

    Rounded for the assertion because the function returns a Decimal carrying
    the full conversion. The point of the test is the equation, not the tail.
    """
    assert round(basal_metabolic_rate(answers())) == 1660


def test_mifflin_for_a_woman():
    """135 lb, 5'5", 30. Same equation, constant of -161 instead of +5."""
    person = answers(sex=Sex.FEMALE, height_in=65, weight_lb=Decimal("135"), age=30)

    assert round(basal_metabolic_rate(person)) == 1333


def test_the_sex_constant_is_the_only_difference():
    """166 kcal apart, always, whatever else changes.

    Worth pinning as a property rather than a number. The equation's sex term is
    a flat constant, so anything that made it scale would be a misreading of the
    formula rather than a tuning choice.
    """
    male = basal_metabolic_rate(answers(sex=Sex.MALE))
    female = basal_metabolic_rate(answers(sex=Sex.FEMALE))

    assert male - female == Decimal("166")


@pytest.mark.parametrize(
    ("activity", "expected"),
    [
        (Activity.SEDENTARY, 1992),
        (Activity.LIGHT, 2283),
        (Activity.MODERATE, 2573),
        (Activity.VERY_ACTIVE, 2864),
    ],
)
def test_every_activity_level_multiplies_the_baseline(activity, expected):
    assert round(maintenance_calories(answers(activity=activity))) == expected


# --- the goal ----------------------------------------------------------------


def test_cutting_takes_twenty_percent_off_maintenance():
    person = answers(goal=Goal.CUT)

    assert baseline_targets(person).calories == round(maintenance_calories(person) * Decimal("0.8"))


def test_maintaining_changes_nothing():
    person = answers(goal=Goal.MAINTAIN)

    assert baseline_targets(person).calories == round(maintenance_calories(person))


def test_gaining_adds_ten_percent():
    person = answers(goal=Goal.GAIN)

    assert baseline_targets(person).calories == round(maintenance_calories(person) * Decimal("1.1"))


def test_the_surplus_is_smaller_than_the_deficit():
    """Not symmetric, and the asymmetry is the decision.

    A body builds muscle at a rate it sets. Calories past that rate become fat,
    so there is less to gain from rushing a bulk than from rushing a cut.
    """
    maintenance = maintenance_calories(answers())
    cut = maintenance - baseline_targets(answers(goal=Goal.CUT)).calories
    gain = baseline_targets(answers(goal=Goal.GAIN)).calories - maintenance

    assert gain < cut


def test_the_adjustment_is_a_share_of_maintenance_not_a_fixed_number():
    """A flat 500 kcal deficit is gentle at 250 lb and brutal at 120 lb.

    Two people of very different sizes should lose different absolute amounts,
    which is what a percentage produces and a constant does not.
    """
    small = answers(weight_lb=Decimal("120"))
    large = answers(weight_lb=Decimal("250"))

    small_deficit = maintenance_calories(small) - baseline_targets(small).calories
    large_deficit = maintenance_calories(large) - baseline_targets(large).calories

    assert large_deficit > small_deficit


# --- protein and fiber -------------------------------------------------------


def test_protein_is_higher_while_cutting():
    """1.0 g/lb cutting against 0.8 otherwise.

    Protein matters most when calories are scarce, which is when the body will
    otherwise take the difference out of muscle.
    """
    cutting = baseline_targets(answers(goal=Goal.CUT)).protein_g
    maintaining = baseline_targets(answers(goal=Goal.MAINTAIN)).protein_g

    assert cutting == 155
    assert maintaining == 124
    assert cutting > maintaining


def test_fiber_follows_the_calorie_target_not_body_weight():
    """14 g per 1,000 kcal, and it reads the *adjusted* calories.

    A dieting user eats less, so they get less fiber. Keying it to weight would
    miss that, and keying it to maintenance would give a cutting user the fiber
    for a day they are not eating.
    """
    cutting = baseline_targets(answers(goal=Goal.CUT))
    maintaining = baseline_targets(answers(goal=Goal.MAINTAIN))

    assert cutting.fiber_g == round(Decimal(cutting.calories) * 14 / 1000)
    assert cutting.fiber_g < maintaining.fiber_g


# --- the formula agrees with its own guardrails -------------------------------


@pytest.mark.parametrize("sex", list(Sex))
@pytest.mark.parametrize("goal", list(Goal))
@pytest.mark.parametrize("activity", list(Activity))
def test_the_formula_never_produces_an_impossible_target(sex, goal, activity):
    """Across the whole supported weight band, on every combination.

    **If our own formula tripped our own absolute range, one of the two would be
    wrong.** The absolute range is a refusal, so a proposal outside it would be a
    number the app suggests and then rejects when the user accepts it.

    The suggested range is different and is allowed to bite: it is advice, and
    `proposal_calorie_range` exists precisely because one part of it disagrees
    with the formula at high weights.
    """
    for pounds in range(int(MINIMUM_SUPPORTED_WEIGHT_LB), int(MAXIMUM_SUPPORTED_WEIGHT_LB) + 1, 5):
        person = answers(
            sex=sex, goal=goal, activity=activity, weight_lb=Decimal(pounds), height_in=70, age=30
        )
        result = propose(person).targets

        assert ABSOLUTE_CALORIE_RANGE[0] <= result.calories <= ABSOLUTE_CALORIE_RANGE[1]
        assert absolute_protein_range(person.weight_lb).contains(result.protein_g)
        assert absolute_fiber_range().contains(result.fiber_g)


def test_an_ordinary_person_is_not_clamped_at_all():
    """The guardrails should be invisible to almost everyone.

    A formula that needed correcting on a mid-sized adult would mean the
    constants and the bounds were tuned against different assumptions.
    """
    result = propose(answers())

    assert result.clamped is False
    assert result.targets == result.baseline
    assert result.targets.calories == 2059


def test_a_small_sedentary_cutter_is_raised_to_the_floor():
    """The clamp doing the job it exists for.

    110 lb, sedentary, cutting works out at 1,164, and 1,200 is the lowest this
    app will suggest for a woman.
    """
    person = answers(
        sex=Sex.FEMALE, height_in=62, weight_lb=Decimal("110"), age=22, activity=Activity.SEDENTARY
    )

    result = propose(person)

    assert result.baseline.calories == 1164
    assert result.targets.calories == 1200
    assert result.clamped is True


def test_a_very_heavy_cutter_is_not_pushed_into_a_surplus():
    """The bug this ticket found by running the formula rather than reading it.

    A 480 lb man cutting works out at 3,031 against a maintenance of 3,788. The
    *suggested* floor for him is 22 kcal/kg, which is 4,790, so clamping the
    formula to the suggested range raised his deficit into a 1,000 kcal surplus
    and handed it to someone who had asked to lose weight.

    `proposal_calorie_range` keeps the sex floor and drops the per-pound term,
    for the formula's output only. See its docstring.
    """
    person = answers(weight_lb=Decimal("480"), height_in=74, age=40, activity=Activity.SEDENTARY)

    result = propose(person)

    assert result.targets.calories == 3031
    assert result.targets.calories < round(maintenance_calories(person))
    # The suggested floor really is above maintenance here, which is what made
    # this a trap rather than a rounding difference.
    assert suggested_calorie_range(person.profile).floor > round(maintenance_calories(person))


def test_an_active_user_is_not_clamped_below_what_they_burn():
    """The mirror of the 480 lb bug, and it hits an ordinary profile.

    The suggested ceiling is 40 kcal/kg, which is 2,812 for a 155 lb man. A very
    active one burns 2,864. So "eat roughly what you burn" was clamped *down*,
    on a completely normal person rather than an extreme.

    Both crossings are the same mistake: a per-pound heuristic applied on top of
    a formula that already accounts for body size.
    """
    person = answers(goal=Goal.MAINTAIN, activity=Activity.VERY_ACTIVE)

    result = propose(person)

    assert result.clamped is False
    assert result.targets.calories == round(maintenance_calories(person))
    # The suggested ceiling really is below maintenance here.
    assert suggested_calorie_range(person.profile).ceiling < result.targets.calories


def test_the_clamp_direction_is_read_rather_than_assumed():
    """A lowered target must not claim the answers worked out lower.

    The second version of the clamped sentence handled only a raise. Nothing
    reaches the ceiling now that it is the absolute 5,000, so this asserts the
    branch directly rather than waiting for a profile that trips it.
    """
    person = answers()
    lowered = explain(person, Targets(4000, 155, 56), Targets(9999, 155, 140))
    raised = explain(person, Targets(1200, 155, 17), Targets(900, 155, 13))

    assert "worked out higher" in lowered
    assert "worked out lower" in raised


def test_the_user_facing_suggested_range_is_left_alone():
    """Only the formula is exempt from the per-pound floor, not the warning.

    A heavy person who types 1,400 by hand should still be told it is low. The
    exemption is about our own arithmetic, which already accounts for body size
    through Mifflin.
    """
    person = answers(weight_lb=Decimal("480"))

    assert suggested_calorie_range(person.profile).floor == 4790
    assert suggested_protein_range(person.profile).floor > 0
    assert suggested_fiber_range(2000).floor == 20


# --- the rationale -----------------------------------------------------------
#
# The prose gets its own tests, not just the numbers. A template that renders
# "minus 0% for your goal" on a maintain plan is a bug no numeric assertion
# catches, and it is the exact failure a format-string-with-holes produces.


def test_every_figure_in_the_rationale_is_a_number_returned_beside_it():
    """The whole argument for a template over a model, asserted.

    A model gets told about the numbers and writes prose around them. A template
    reads them, so it cannot name a figure that is not on the screen.
    """
    result = propose(answers())

    assert f"{result.targets.calories:,}" in result.rationale
    assert f"{result.targets.protein_g} g" in result.rationale
    assert f"{result.targets.fiber_g} g" in result.rationale


def test_a_maintain_plan_mentions_no_deficit_and_no_rate():
    """The sentence that betrays a template written as arithmetic.

    There is no percentage to state and no weekly change to promise, so the
    branch says something else entirely rather than substituting a zero.
    """
    rationale = propose(answers(goal=Goal.MAINTAIN)).rationale

    assert "%" not in rationale
    assert "a week" not in rationale
    assert "roughly what you burn" in rationale


def test_a_cut_names_the_deficit_and_the_rate():
    rationale = propose(answers(goal=Goal.CUT)).rationale

    assert "20% below" in rationale
    assert "1.0 lb a week" in rationale


def test_a_gain_counts_up_rather_than_down():
    rationale = propose(answers(goal=Goal.GAIN)).rationale

    assert "10% above" in rationale
    assert "below" not in rationale


def test_the_prose_follows_the_numbers_when_an_input_changes():
    """Change the weight, and the paragraph changes with it.

    A template that had drifted from the calculation would keep saying the old
    figure while the numbers beside it moved.
    """
    lighter = propose(answers(weight_lb=Decimal("140")))
    heavier = propose(answers(weight_lb=Decimal("200")))

    assert lighter.rationale != heavier.rationale
    assert f"{heavier.targets.protein_g} g" in heavier.rationale
    assert f"{heavier.targets.protein_g} g" not in lighter.rationale


def test_the_rationale_does_not_describe_a_number_the_clamp_replaced():
    """The second bug this ticket found by running it.

    The first version wrote the sentence from the answers and the number from
    the clamp, so a user whose calories were raised read "1,200 calories a day.
    That is 20% below the 1,455 you burn". 1,200 is not 20% below 1,455.
    """
    person = answers(
        sex=Sex.FEMALE, height_in=62, weight_lb=Decimal("110"), age=22, activity=Activity.SEDENTARY
    )

    result = propose(person)

    assert result.clamped is True
    assert "20% below" not in result.rationale
    assert "1,200 calories a day" in result.rationale
    assert "least this app will suggest" in result.rationale


def test_the_protein_reason_changes_with_the_goal():
    """Two different reasons, because the number is chosen for two reasons."""
    cutting = propose(answers(goal=Goal.CUT)).rationale
    maintaining = propose(answers(goal=Goal.MAINTAIN)).rationale

    assert "holding on to muscle" in cutting
    assert "holding on to muscle" not in maintaining
    assert "1.0 g per pound" in cutting
    assert "0.8 g per pound" in maintaining
