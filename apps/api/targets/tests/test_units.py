"""Guards against values that live in two apps drifting apart.

`accounts` owns the `sex` column and the weight bounds. `targets.services` owns
the arithmetic those values feed. Each needs the same facts, and neither can
import the other: `targets` holds a foreign key to `accounts`, so an import back
would invert the app order doc 02 sets out and reorder the migrations.

So the values are written twice, which is a real cost and the honest one. These
tests are what make the duplication safe rather than a bug waiting for whoever
edits one side.

They fail only when the two stop agreeing, which is the one moment it matters.
"""

from decimal import Decimal
from typing import cast

from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Field

from accounts.models import Sex as StoredSex
from targets.services import (
    MAXIMUM_SUPPORTED_WEIGHT_LB,
    MINIMUM_SUPPORTED_WEIGHT_LB,
    SUGGESTED_CALORIE_FLOOR_BY_SEX,
)
from targets.services import Sex as ComputedSex

User = get_user_model()


def _bound(validator_class, field_name: str = "current_weight_lb") -> Decimal:
    """The limit a named validator puts on a model field."""
    # get_field returns a union that includes reverse relations, which have no
    # validators. Every name this helper is called with is a concrete field.
    field = cast(Field, User._meta.get_field(field_name))
    limit = next(v.limit_value for v in field.validators if isinstance(v, validator_class))
    return Decimal(limit)


# --- the two Sex enums --------------------------------------------------------


def test_the_two_sex_enums_hold_the_same_values():
    """`accounts.models.Sex` is a Django `TextChoices` because it backs a column.
    `targets.services.Sex` is a plain `StrEnum` because that module is pure
    functions with no Django in it. A stored value has to satisfy the arithmetic,
    so the strings must match exactly."""
    assert {choice.value for choice in StoredSex} == {member.value for member in ComputedSex}


def test_every_stored_sex_is_one_the_calorie_floors_know():
    """The sharper version of the test above. A value could exist in both enums
    and still have no calorie floor behind it, which would be a `KeyError` deep
    inside a range function rather than a validation error at the edge."""
    for choice in StoredSex:
        assert ComputedSex(choice.value) in SUGGESTED_CALORIE_FLOOR_BY_SEX


# --- the weight band ----------------------------------------------------------


def test_the_stored_weight_floor_matches_the_computed_precondition():
    """`current_weight_lb` must not accept a weight the clamp refuses to work
    with.

    Below 85 lb the suggested calorie floor passes the ceiling and
    `suggested_calorie_range` raises. If the model validator drops below it, a
    user could store a weight that turns a 400 at the edge into a 500 in the
    middle.
    """
    assert _bound(MinValueValidator) == Decimal(MINIMUM_SUPPORTED_WEIGHT_LB)


def test_the_stored_weight_ceiling_matches_the_computed_precondition():
    """The other end, and the one review had to find because I pinned only the
    first.

    The suggested calorie ceiling stops at 5,000 while its floor keeps climbing,
    so they cross again at 501.05 lb. The original 1000 lb validator accepted
    weights that made `suggested_calorie_range` raise, which is the exact failure
    the floor was added to prevent, at the opposite end.

    A bound that clamps against a constant while its opposite scales freely will
    cross somewhere. Pinning one end and not the other is how the second crossing
    survives a review.
    """
    assert _bound(MaxValueValidator) == Decimal(MAXIMUM_SUPPORTED_WEIGHT_LB)


def test_both_weight_columns_share_one_band():
    """`goal_weight_lb` and `current_weight_lb` measure the same thing in the
    same unit, so disagreeing would need a reason. There is not one.

    The first version had 44 to 880 on the goal and 85 to 1000 on the current,
    because the goal bounds were carried across from kilograms and nobody ever
    picked them in pounds. A goal of 44 lb passed while a current weight of 44 lb
    failed.
    """
    for validator in (MinValueValidator, MaxValueValidator):
        assert _bound(validator, "goal_weight_lb") == _bound(validator, "current_weight_lb")
