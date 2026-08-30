"""Guards against two pairs of values drifting apart.

`accounts` owns the `sex` column and the weight bounds. `targets.services` owns
the arithmetic those values feed. Each needs the same facts, and neither can
import the other: `targets` holds a foreign key to `accounts`, so an import back
the other way inverts the app dependency doc 02 sets out and would reorder the
migrations.

So the values are written twice, which is a real cost and the honest one. These
tests are what makes the duplication safe rather than a bug waiting for whoever
edits one side.

Both would pass silently if someone deleted the other side's constant and
retyped it. That is the point: they fail when the two stop agreeing, which is the
only moment it matters.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

from accounts.models import Sex as StoredSex
from targets.services import MINIMUM_SUPPORTED_WEIGHT_LB
from targets.services import Sex as ComputedSex

User = get_user_model()


def test_the_two_sex_enums_hold_the_same_values():
    """`accounts.models.Sex` is a Django `TextChoices` because it backs a column.
    `targets.services.Sex` is a plain `StrEnum` because that module is pure
    functions with no Django in it. The stored value has to satisfy the
    arithmetic, so the strings must match exactly."""
    assert {choice.value for choice in StoredSex} == {member.value for member in ComputedSex}


def test_every_stored_sex_is_one_the_calorie_floors_know():
    """The sharper version of the test above. A value could exist in both enums
    and still have no calorie floor behind it, which would be a `KeyError` deep
    inside a range function rather than a validation error at the edge."""
    from targets.services import SUGGESTED_CALORIE_FLOOR_BY_SEX

    for choice in StoredSex:
        assert ComputedSex(choice.value) in SUGGESTED_CALORIE_FLOOR_BY_SEX


def test_the_stored_weight_floor_matches_the_computed_precondition():
    """`current_weight_lb` cannot accept a weight the clamp refuses to work with.

    85 lb is `targets.services`'s stated precondition: below it the suggested
    calorie floor passes the ceiling and the range inverts. If the model's
    validator ever drops below it, a user could store a weight that makes
    `suggested_calorie_range` raise, turning a 400 at the edge into a 500 in the
    middle.
    """
    field = User._meta.get_field("current_weight_lb")
    minimum = next(v.limit_value for v in field.validators if isinstance(v, MinValueValidator))

    assert Decimal(minimum) == Decimal(MINIMUM_SUPPORTED_WEIGHT_LB)
