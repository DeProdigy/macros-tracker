from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from accounts.models import User
from targets.models import TargetVersion

from .models import DailyLog, FoodEntry, FoodItem

TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class ManualItem:
    name: str
    quantity: Decimal
    calories: Decimal
    protein_g: Decimal
    fiber_g: Decimal


def _total(value: Decimal, quantity: Decimal) -> Decimal:
    return (value * quantity).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def create_manual_entry(
    *, user: User, local_date: date, eaten_at: datetime, item: ManualItem
) -> FoodEntry:
    target = (
        TargetVersion.objects.filter(user=user, effective_from__lte=local_date)
        .order_by("-effective_from", "-created_at", "-id")
        .first()
    )
    day, _ = DailyLog.objects.get_or_create(
        user=user, local_date=local_date, defaults={"target_version": target}
    )
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.MANUAL,
        description=item.name,
        eaten_at=eaten_at,
        calories=_total(item.calories, item.quantity),
        protein_g=_total(item.protein_g, item.quantity),
        fiber_g=_total(item.fiber_g, item.quantity),
    )
    FoodItem.objects.create(entry=entry, portion_label="", **item.__dict__)
    return entry
