import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from accounts.models import User
from ai.models import FoodAnalysisCall
from targets.models import TargetVersion
from uploads.services import copy_analysis_object_to_entry, delete_object

from .models import DailyLog, FoodEntry, FoodItem

TWOPLACES = Decimal("0.01")
logger = logging.getLogger(__name__)


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
    target = TargetVersion.objects.effective_on(user, local_date)
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
    FoodItem.objects.create(
        entry=entry,
        portion_label="",
        name=item.name,
        quantity=item.quantity,
        calories=item.calories,
        protein_g=item.protein_g,
        fiber_g=item.fiber_g,
    )
    return entry


@transaction.atomic
def _store_photo_entry(
    *, user: User, local_date: date, eaten_at: datetime, call_id: int, photo_key: str
) -> tuple[FoodEntry, str]:
    call = FoodAnalysisCall.objects.select_for_update().get(
        pk=call_id, user=user, status=FoodAnalysisCall.Status.SUCCEEDED
    )
    if hasattr(call, "food_entry"):
        raise ValueError("This analysis was already saved.")
    response = call.response_payload or {}
    items = response.get("items", [])
    if not items:
        raise ValueError("This analysis has no validated items.")
    target = TargetVersion.objects.effective_on(user, local_date)
    day, _ = DailyLog.objects.get_or_create(
        user=user, local_date=local_date, defaults={"target_version": target}
    )
    description = str(call.request_payload.get("description", "")).strip()
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.PHOTO,
        description=description or ", ".join(str(item["name"]) for item in items)[:200],
        eaten_at=eaten_at,
        calories=sum((Decimal(str(item["calories"])) for item in items), Decimal("0")),
        protein_g=sum((Decimal(str(item["protein_g"])) for item in items), Decimal("0")),
        fiber_g=sum((Decimal(str(item["fiber_g"])) for item in items), Decimal("0")),
        photo_key=photo_key,
        analysis_call=call,
    )
    FoodItem.objects.bulk_create(
        [
            FoodItem(
                entry=entry,
                name=item["name"],
                portion_label=item["portion"],
                quantity=Decimal("1.00"),
                calories=Decimal(str(item["calories"])),
                protein_g=Decimal(str(item["protein_g"])),
                fiber_g=Decimal(str(item["fiber_g"])),
            )
            for item in items
        ]
    )
    old_key = str(call.request_payload["photo_key"])
    call.request_payload = {**call.request_payload, "photo_key": photo_key}
    call.save(update_fields=("request_payload",))
    return entry, old_key


def create_photo_entry(
    *, user: User, local_date: date, eaten_at: datetime, analysis_id: int
) -> FoodEntry:
    call = FoodAnalysisCall.objects.get(
        pk=analysis_id, user=user, status=FoodAnalysisCall.Status.SUCCEEDED
    )
    old_key = str(call.request_payload["photo_key"])
    try:
        entry_key = copy_analysis_object_to_entry(key=old_key, user_id=user.pk)
    except Exception:
        # Another save may have committed and removed the analysis source after
        # this request read its key. Report the stable already-saved result.
        if FoodEntry.objects.filter(analysis_call_id=analysis_id).exists():
            raise ValueError("This analysis was already saved.") from None
        raise
    try:
        entry, committed_old_key = _store_photo_entry(
            user=user,
            local_date=local_date,
            eaten_at=eaten_at,
            call_id=analysis_id,
            photo_key=entry_key,
        )
    except Exception:
        # A concurrent save can have committed this deterministic key while this
        # request waited on the analysis row lock. Never delete that entry's photo.
        committed = FoodEntry.objects.filter(
            analysis_call_id=analysis_id, photo_key=entry_key
        ).exists()
        if not committed:
            delete_object(key=entry_key)
        raise
    try:
        delete_object(key=committed_old_key)
    except Exception:
        # The entry key is already committed. The analysis copy is now an orphan,
        # not a reason to tell the client that its successful save failed.
        logger.exception("Could not delete the replaced analysis photo object.")
    return entry
