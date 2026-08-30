"""The two-tier guardrail on daily macro targets.

Pure functions. No HTTP, no database, no model provider. Everything here is
arithmetic and comparison, which is why it is the most thoroughly tested module
in the epic and the thing the AI path falls back to when it misbehaves.

**Everything here is pounds.** Weight comes in as pounds and every bound is per
pound. This is a US app and the whole stack speaks pounds, from the onboarding
stepper to the wire format to this module. Nothing converts at request time.

`_per_pound` is not a unit conversion in the runtime sense and **should not be
deleted**. It has been removed twice already, once on the reasoning that the
module should "just default to pounds". It does. The helper runs at import and
exists so the published figure a bound came from stays readable: `1.6` can be
looked up in a paper, and `0.72574779` cannot be looked up anywhere. Deleting it
leaves comments pointing at numbers that are no longer in the file, which is what
happened last time.

**Two ranges, not one**, ruled 29 Aug 2026. One range forces a choice between
two bad outcomes: clamp everything, and a person eating 1,400 kcal under medical
supervision cannot record it while the app silently rewrites their number; clamp
nothing the user typed, and someone sets 400 kcal.

    suggested   Advice. AI output is clamped into it, always. A user who steps
                outside gets a warning and their number is saved as typed.
    absolute    A refusal. Nothing crosses it, not the model and not the user.
                Outside it the request is rejected, never silently corrected.

The two answer different questions. "Is this a sensible target?" is one a person
is allowed to disagree with. "Is this a target at all?" is not.

Which caller clamps and which refuses is a decision at the call site rather than
a flag in here. `clamp_to_suggested` and `reject_outside_absolute` are separate
functions on purpose: a `strict=True` argument would bury the most interesting
line of the design inside a boolean.

Failures raise DRF's ValidationError with a distinct `code`, matching
`accounts/services.py`. That lets MAC-40's serializer return a 400 without
translating anything.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from rest_framework.exceptions import ValidationError

# Pounds in a kilogram. The one place this module names another unit, and it
# names it to get rid of it: every bound below is per pound by the time anything
# reads it.
_POUNDS_PER_KG = Decimal("2.20462262")


def _per_pound(published_per_kg: str) -> Decimal:
    """Turn a published per-kilogram figure into the per-pound bound we use.

    Runs once at import. Nothing converts per request.

    The argument is the number to look up. Nutrition research publishes protein
    intake per kilogram, so `1.6` is findable in a paper and `0.72574779` is
    findable nowhere. Writing the literal would make every bound in this module
    uncheckable, and the comments beside them would describe a figure the file no
    longer contains.
    """
    return Decimal(published_per_kg) / _POUNDS_PER_KG


# --- what the bounds are made of ---------------------------------------------
#
# Honesty about provenance, because these numbers will be questioned later and
# "the ticket said so" is not an answer. Two of them are well supported by
# evidence. The rest are judgement calls, and the comments say which is which.


class Sex(StrEnum):
    """Biological sex, as Mifflin-St Jeor and the calorie floors need it.

    **Mirrors `accounts.models.Sex`, which is canonical and backs the `User.sex`
    column.** A plain `StrEnum` here rather than Django's `TextChoices`, because
    this module is pure functions with no Django in it.

    `targets` holds a foreign key to `accounts`, so importing the real one back
    would invert the app order doc 02 sets out. The values are written twice
    instead, and `targets/tests/test_units.py` asserts they agree.

    An earlier version of this docstring said the six onboarding answers are not
    persisted. Two of them are, as of MAC-53.
    """

    FEMALE = "female"
    MALE = "male"


# Calories per pound of body weight, for the suggested range.
#
# **Judgement, not a citation.** 22 kcal/kg lands near an aggressive but ordinary
# cut and 40 near a generous bulk. Doc 15's prototype used a fixed 1,500-3,200,
# which is right for a mid-sized adult and wrong at both ends: it forbids a
# 110 lb woman a sensible target and warns a 220 lb man about a reasonable one.
SUGGESTED_CALORIES_PER_LB = (_per_pound("22"), _per_pound("40"))

# A floor under the per-pound figure, because the ratio gets very low for a small
# person. **Rules of thumb**, widely repeated in consumer nutrition guidance
# rather than drawn from one authority. Treat them as such.
SUGGESTED_CALORIE_FLOOR_BY_SEX = {
    Sex.FEMALE: 1200,
    Sex.MALE: 1500,
}

# Protein per pound, for the suggested range.
#
# **The best-supported numbers in this module.** 1.6 to 2.2 g/kg for muscle
# retention in a deficit is replicated across many trials. The ceiling is widened
# to 2.5 deliberately: the evidence says there is no *added* benefit above 2.2,
# not that 2.4 is unwise, and warning a high-protein eater on every save trains
# them to ignore the warning that matters.
SUGGESTED_PROTEIN_G_PER_LB = (_per_pound("1.6"), _per_pound("2.5"))

# Fiber per 1,000 kcal, for the suggested range.
#
# **14 g per 1,000 kcal is the US Dietary Guidelines figure**, and the band here
# brackets it. Note what this keys off: fiber scales with the *calorie target*,
# not with body weight. A 1,400 kcal day and a 3,000 kcal day genuinely need
# different amounts, and tying fiber to weight would miss that. No pound
# conversion, because the guideline is already written per calorie.
SUGGESTED_FIBER_G_PER_1000_KCAL = (Decimal("10"), Decimal("20"))

# The absolute range. Nothing crosses it.
#
# The 1,000 floor is the owner's call, and it is a judgement rather than a
# clinical citation. Under roughly 800 kcal is medically supervised territory a
# phone app has no business in; 1,000 sits below every ordinary aggressive cut
# while still refusing the genuinely dangerous. The 5,000 ceiling is the owner's
# too, and it is there to catch a typo rather than to police an athlete.
ABSOLUTE_CALORIE_RANGE = (1000, 5000)

# Wide on purpose. 0.5 g/kg is below the RDA and 3.5 is above any studied
# benefit, so a value outside this is a mistyped number rather than a preference.
ABSOLUTE_PROTEIN_G_PER_LB = (_per_pound("0.5"), _per_pound("3.5"))

# Zero is allowed: a user may not want a fiber target at all, and refusing that
# would be the app having an opinion where it has no standing. 100 g is roughly
# three times the guideline intake, which makes it a typo.
ABSOLUTE_FIBER_RANGE = (0, 100)

# The weight band the suggested calorie range can actually describe. Outside it
# the floor and the ceiling cross and `Range` raises.
#
# **It inverts at both ends, for opposite reasons.** At the bottom the fixed sex
# floor passes the per-pound ceiling: 82.67 lb for a man, 66.14 lb for a woman.
# At the top the ceiling stops at ABSOLUTE_CALORIE_RANGE's 5,000 while the floor
# keeps climbing, so they cross again at 501.05 lb.
#
# Review found the top one after the bottom one had already shipped, which is the
# second time this shape has caught me out. A bound that clamps against a
# constant while its opposite scales freely will cross somewhere. The only
# question is whether anyone looked at both ends.
#
# 85 and 500 sit inside both crossings with room. `accounts.User` enforces them
# on the column, and `targets/tests/test_units.py` pins the pair together.
MINIMUM_SUPPORTED_WEIGHT_LB = Decimal("85")
MAXIMUM_SUPPORTED_WEIGHT_LB = Decimal("500")


# --- value types -------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    """Everything the bounds depend on, and nothing else.

    Deliberately smaller than the six onboarding answers. Age, height, goal, and
    activity feed Mifflin-St Jeor in MAC-51; none of them changes what counts as
    a safe target. Passing the whole answer set here would imply they do.

    **A weight between `MINIMUM_SUPPORTED_WEIGHT_LB` and
    `MAXIMUM_SUPPORTED_WEIGHT_LB` is a precondition**, not a suggestion. Outside
    that band the suggested calorie floor and ceiling cross and the range
    inverts. See those constants for both crossings.

    `User.current_weight_lb` carries the same bounds as validators, so a bad
    weight is a 400 at the edge rather than a 500 from in here.
    `Range.__post_init__` is the backstop for a caller that builds a `Profile`
    some other way, and it raises rather than repairing: silently widening the
    ceiling to meet the floor would invent a recommendation for a body these
    numbers were never derived for.

    The realistic trigger is a typo, not an unusual person. 70 instead of 170 at
    the bottom, 1000 instead of 100.0 at the top.
    """

    sex: Sex
    weight_lb: Decimal


@dataclass(frozen=True)
class Targets:
    calories: int
    protein_g: int
    fiber_g: int


@dataclass(frozen=True)
class Range:
    """A floor and a ceiling, named, and checked.

    A plain tuple would be cheaper and `bounds[0]` at a call site tells the
    reader nothing. Worse, swapping floor and ceiling would pass every type
    check and every linter.

    So would **crossing** them, which is the same thought carried one step
    further. An inverted range fails silently in both directions: `clamp` returns
    the floor for every input and ignores the ceiling, and `contains` returns
    False for every input. Nothing raises, nothing logs, and the numbers are
    quietly wrong.

    The guard makes that impossible for all six range functions at once, rather
    than for the one that happened to have the bug.
    """

    floor: int
    ceiling: int

    def __post_init__(self) -> None:
        if self.floor > self.ceiling:
            raise ValueError(f"Range floor {self.floor} is above ceiling {self.ceiling}.")

    def clamp(self, value: int) -> int:
        return max(self.floor, min(self.ceiling, value))

    def contains(self, value: int) -> bool:
        return self.floor <= value <= self.ceiling


@dataclass(frozen=True)
class Adjustment:
    """One field the clamp moved, and where it moved it from."""

    field: str
    original: int
    clamped: int


@dataclass(frozen=True)
class ClampResult:
    targets: Targets
    adjustments: tuple[Adjustment, ...]

    @property
    def changed(self) -> bool:
        """Whether anything moved.

        The caller needs this rather than comparing target sets itself. MAC-41
        logs an out-of-bounds model response and falls back to the deterministic
        numbers, and doc 15's result screen shows `BASELINE 2180 -> SET 2150`.
        Both need to know a change happened, and both want to know which field.
        """
        return bool(self.adjustments)


# --- rounding ----------------------------------------------------------------
#
# Per-pound arithmetic produces fractions and targets are whole numbers, so every
# bound gets rounded. The direction is not arbitrary.
#
# **Floors round up, ceilings round down.** Both tighten the range. Rounding a
# floor down would let a value through that the unrounded bound refuses, which
# weakens a safety control by a calorie. The amount is silly; the direction is
# the point, and it is the kind of thing that gets "simplified" to round() by
# someone tidying up later.


def _floor_of(value: Decimal) -> int:
    return math.ceil(value)


def _ceiling_of(value: Decimal) -> int:
    return math.floor(value)


# --- the suggested range -----------------------------------------------------
#
# One function per macro rather than one returning all three, because they do not
# take the same inputs. Calories and protein scale with body weight; fiber scales
# with the calorie target. A single `suggested_bounds(profile)` would have to
# hide the calorie dependency, and hiding it is how someone later computes fiber
# against the wrong number.
#
# Every suggested range nests inside its absolute counterpart **by construction**,
# with a `min` and a `max`, rather than by an ordering the caller has to get
# right. A suggested range that leaves the absolute one recommends a number the
# write path refuses, and the first person to hit it is someone the design never
# pictured.


def suggested_calorie_range(profile: Profile) -> Range:
    """The calorie band a target is expected to sit in.

    Two crossings to keep in view, and they are mirror images.

    At the top, the per-pound ceiling passes 5,000 at about 276 lb. The `min`
    stops the app suggesting more than its own write path allows.

    At the bottom, the fixed sex floor passes the per-pound ceiling at 82.67 lb
    for a man and 66.14 lb for a woman, and the range inverts. The `min` above
    creates a third crossing at the top: the ceiling stops at 5,000 while the
    floor keeps climbing, so they meet again at 501.05 lb.

    Neither inversion is repaired here. `Profile` states the band,
    `User.current_weight_lb` enforces it, and `Range.__post_init__` raises if
    both are bypassed.
    """
    per_lb_floor, per_lb_ceiling = SUGGESTED_CALORIES_PER_LB
    absolute = absolute_calorie_range()

    return Range(
        floor=max(
            _floor_of(per_lb_floor * profile.weight_lb),
            SUGGESTED_CALORIE_FLOOR_BY_SEX[profile.sex],
        ),
        ceiling=min(_ceiling_of(per_lb_ceiling * profile.weight_lb), absolute.ceiling),
    )


def suggested_protein_range(profile: Profile) -> Range:
    per_lb_floor, per_lb_ceiling = SUGGESTED_PROTEIN_G_PER_LB
    absolute = absolute_protein_range(profile)

    return Range(
        floor=max(_floor_of(per_lb_floor * profile.weight_lb), absolute.floor),
        ceiling=min(_ceiling_of(per_lb_ceiling * profile.weight_lb), absolute.ceiling),
    )


def suggested_fiber_range(calories: int) -> Range:
    """Keyed on the calorie target, not on body weight. See the constant.

    Nested inside the absolute fiber range for the same reason the calorie one
    is. This function is public, so a caller can hand it an unclamped number:
    `suggested_fiber_range(6000)` would otherwise return a ceiling of 120 when
    the write path refuses anything over 100.

    Inside `clamp_to_suggested` the calorie clamp runs first and hides that.
    Relying on call order to keep a public function honest is how the order
    eventually gets changed by someone who does not know it was load-bearing.
    """
    per_1000_floor, per_1000_ceiling = SUGGESTED_FIBER_G_PER_1000_KCAL
    absolute = absolute_fiber_range()
    thousands = Decimal(calories) / Decimal(1000)

    return Range(
        floor=max(_floor_of(per_1000_floor * thousands), absolute.floor),
        ceiling=min(_ceiling_of(per_1000_ceiling * thousands), absolute.ceiling),
    )


# --- the absolute range ------------------------------------------------------


def absolute_calorie_range() -> Range:
    floor, ceiling = ABSOLUTE_CALORIE_RANGE
    return Range(floor=floor, ceiling=ceiling)


def absolute_protein_range(profile: Profile) -> Range:
    per_lb_floor, per_lb_ceiling = ABSOLUTE_PROTEIN_G_PER_LB
    return Range(
        floor=_floor_of(per_lb_floor * profile.weight_lb),
        ceiling=_ceiling_of(per_lb_ceiling * profile.weight_lb),
    )


def absolute_fiber_range() -> Range:
    floor, ceiling = ABSOLUTE_FIBER_RANGE
    return Range(floor=floor, ceiling=ceiling)


# --- the two entry points ----------------------------------------------------


def clamp_to_suggested(targets: Targets, profile: Profile) -> ClampResult:
    """Pull a target set into the suggested range, reporting what moved.

    For model output only. A user's own number goes to `reject_outside_absolute`
    and is stored as typed.

    Calories are clamped first, and fiber's range is then derived from the
    *clamped* calorie value rather than the one that arrived. A model that asks
    for 6,000 kcal and 110 g of fiber should be judged on the 5,000 it actually
    gets, not on the number it was refused.
    """
    adjustments: list[Adjustment] = []

    def apply(field: str, value: int, allowed: Range) -> int:
        clamped = allowed.clamp(value)
        if clamped != value:
            adjustments.append(Adjustment(field=field, original=value, clamped=clamped))
        return clamped

    calories = apply("calories", targets.calories, suggested_calorie_range(profile))
    protein_g = apply("protein_g", targets.protein_g, suggested_protein_range(profile))
    fiber_g = apply("fiber_g", targets.fiber_g, suggested_fiber_range(calories))

    return ClampResult(
        targets=Targets(calories=calories, protein_g=protein_g, fiber_g=fiber_g),
        adjustments=tuple(adjustments),
    )


def reject_outside_absolute(targets: Targets, profile: Profile) -> None:
    """Raise if any target is outside the range nothing may cross.

    Rejects rather than clamps, and that is the whole argument. Silently storing
    a different number than the one someone typed is worse than telling them no:
    they walk away believing they set 400 kcal, and nothing on screen disagrees.

    Runs on **every** write, whatever produced the numbers. A model that got past
    the suggested clamp still has to clear this, because the clamp reports rather
    than enforces.
    """
    checks = (
        ("calories", targets.calories, absolute_calorie_range()),
        ("protein_g", targets.protein_g, absolute_protein_range(profile)),
        ("fiber_g", targets.fiber_g, absolute_fiber_range()),
    )

    errors = {
        field: [f"Must be between {allowed.floor} and {allowed.ceiling}. Received {value}."]
        for field, value, allowed in checks
        if not allowed.contains(value)
    }

    if errors:
        # All failing fields at once, not the first. A caller who fixes one and
        # resubmits only to be told about the next has been made to guess.
        raise ValidationError(errors, code="target_out_of_bounds")
