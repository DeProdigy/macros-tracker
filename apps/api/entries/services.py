import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from django.db import transaction
from django.db.models import Q

from accounts.models import User
from ai.models import FoodAnalysisCall
from targets.models import TargetVersion
from uploads.services import copy_analysis_object_to_entry, delete_object

from .models import DailyLog, FoodEntry, FoodItem

TWOPLACES = Decimal("0.01")
MAX_ENTRY_TOTAL = Decimal("99999999.99")
RECENT_FOOD_LIMIT = 100
POSITIVE_MACROS_ERROR = "Enter at least one macro value greater than zero."
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ManualItem:
    name: str
    quantity: Decimal
    calories: Decimal
    protein_g: Decimal
    fiber_g: Decimal


@dataclass(frozen=True)
class EditableItem:
    name: str
    portion_label: str
    quantity: Decimal
    calories: Decimal
    protein_g: Decimal
    fiber_g: Decimal


class ItemWithMacros(Protocol):
    @property
    def quantity(self) -> Decimal: ...

    @property
    def calories(self) -> Decimal: ...

    @property
    def protein_g(self) -> Decimal: ...

    @property
    def fiber_g(self) -> Decimal: ...


class EntryRequiresOneItem(Exception):
    pass


def has_positive_macros(*, calories: Decimal, protein_g: Decimal, fiber_g: Decimal) -> bool:
    return any(value > 0 for value in (calories, protein_g, fiber_g))


def entry_totals(items: Iterable[ItemWithMacros]) -> tuple[Decimal, Decimal, Decimal]:
    calories = Decimal("0")
    protein_g = Decimal("0")
    fiber_g = Decimal("0")
    for item in items:
        calories += item.quantity * item.calories
        protein_g += item.quantity * item.protein_g
        fiber_g += item.quantity * item.fiber_g
    return (
        calories.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        protein_g.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        fiber_g.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
    )


def recalculate_entry_totals(entry: FoodEntry) -> FoodEntry:
    entry.calories, entry.protein_g, entry.fiber_g = entry_totals(entry.items.all())
    entry.save(update_fields=("calories", "protein_g", "fiber_g"))
    return entry


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
        calories=Decimal("0"),
        protein_g=Decimal("0"),
        fiber_g=Decimal("0"),
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
    return recalculate_entry_totals(entry)


def recent_foods(*, user: User, search: str = "") -> list[FoodItem]:
    items = FoodItem.objects.filter(entry__daily_log__user=user)
    normalized_search = search.strip()
    if normalized_search:
        items = items.filter(
            Q(name__icontains=normalized_search) | Q(portion_label__icontains=normalized_search)
        )
    ordered_items = items.only(
        "id", "name", "portion_label", "calories", "protein_g", "fiber_g"
    ).order_by("-entry__eaten_at", "-entry_id", "-id")
    distinct_items: list[FoodItem] = []
    seen: set[tuple[str, str]] = set()
    for item in ordered_items.iterator(chunk_size=RECENT_FOOD_LIMIT):
        key = (item.name.strip().casefold(), item.portion_label.strip().casefold())
        if key in seen:
            continue
        seen.add(key)
        distinct_items.append(item)
        if len(distinct_items) == RECENT_FOOD_LIMIT:
            break
    return distinct_items


@transaction.atomic
def create_recent_entry(
    *,
    user: User,
    local_date: date,
    eaten_at: datetime,
    recent_item_id: int,
    quantity: Decimal,
) -> FoodEntry:
    source_item = FoodItem.objects.get(pk=recent_item_id, entry__daily_log__user=user)
    totals = entry_totals(
        [
            EditableItem(
                name=source_item.name,
                portion_label=source_item.portion_label,
                quantity=quantity,
                calories=source_item.calories,
                protein_g=source_item.protein_g,
                fiber_g=source_item.fiber_g,
            )
        ]
    )
    if any(total > MAX_ENTRY_TOTAL for total in totals):
        raise ValueError("Quantity makes macro totals too large.")
    target = TargetVersion.objects.effective_on(user, local_date)
    day, _ = DailyLog.objects.get_or_create(
        user=user, local_date=local_date, defaults={"target_version": target}
    )
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.RECENT,
        description=source_item.name,
        eaten_at=eaten_at,
        calories=Decimal("0"),
        protein_g=Decimal("0"),
        fiber_g=Decimal("0"),
    )
    FoodItem.objects.create(
        entry=entry,
        name=source_item.name,
        portion_label=source_item.portion_label,
        quantity=quantity,
        calories=source_item.calories,
        protein_g=source_item.protein_g,
        fiber_g=source_item.fiber_g,
    )
    return recalculate_entry_totals(entry)


@transaction.atomic
def _store_photo_entry(
    *,
    user: User,
    local_date: date,
    eaten_at: datetime,
    call_id: int,
    photo_key: str,
    corrected_items: list[EditableItem] | None,
) -> tuple[FoodEntry, str]:
    call = FoodAnalysisCall.objects.select_for_update().get(
        pk=call_id, user=user, status=FoodAnalysisCall.Status.SUCCEEDED
    )
    if hasattr(call, "food_entry"):
        raise ValueError("This analysis was already saved.")
    response = call.response_payload or {}
    analysis_items = response.get("items", [])
    if not analysis_items:
        raise ValueError("This analysis has no validated items.")
    items = (
        corrected_items
        if corrected_items is not None
        else [
            EditableItem(
                name=str(item["name"]),
                portion_label=str(item["portion"]),
                quantity=Decimal("1.00"),
                calories=Decimal(str(item["calories"])),
                protein_g=Decimal(str(item["protein_g"])),
                fiber_g=Decimal(str(item["fiber_g"])),
            )
            for item in analysis_items
        ]
    )
    target = TargetVersion.objects.effective_on(user, local_date)
    day, _ = DailyLog.objects.get_or_create(
        user=user, local_date=local_date, defaults={"target_version": target}
    )
    description = str(call.request_payload.get("description", "")).strip()
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.PHOTO,
        description=description or ", ".join(item.name for item in items)[:200],
        eaten_at=eaten_at,
        calories=Decimal("0"),
        protein_g=Decimal("0"),
        fiber_g=Decimal("0"),
        photo_key=photo_key,
        analysis_call=call,
    )
    FoodItem.objects.bulk_create(
        [
            FoodItem(
                entry=entry,
                name=item.name,
                portion_label=item.portion_label,
                quantity=item.quantity,
                calories=item.calories,
                protein_g=item.protein_g,
                fiber_g=item.fiber_g,
            )
            for item in items
        ]
    )
    recalculate_entry_totals(entry)
    old_key = str(call.request_payload["photo_key"])
    call.request_payload = {**call.request_payload, "photo_key": photo_key}
    call.save(update_fields=("request_payload",))
    return entry, old_key


def create_photo_entry(
    *,
    user: User,
    local_date: date,
    eaten_at: datetime,
    analysis_id: int,
    corrected_items: list[EditableItem] | None = None,
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
            corrected_items=corrected_items,
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


def _locked_entry(*, user: User, entry_id: int) -> FoodEntry:
    return FoodEntry.objects.select_for_update().get(pk=entry_id, daily_log__user=user)


@transaction.atomic
def create_entry_item(*, user: User, entry_id: int, item: EditableItem) -> FoodItem:
    entry = _locked_entry(user=user, entry_id=entry_id)
    created = FoodItem.objects.create(
        entry=entry,
        name=item.name,
        portion_label=item.portion_label,
        quantity=item.quantity,
        calories=item.calories,
        protein_g=item.protein_g,
        fiber_g=item.fiber_g,
    )
    recalculate_entry_totals(entry)
    return created


@transaction.atomic
def update_entry_item(
    *, user: User, entry_id: int, item_id: int, changes: dict[str, str | Decimal]
) -> FoodItem:
    entry = _locked_entry(user=user, entry_id=entry_id)
    item = FoodItem.objects.get(pk=item_id, entry=entry)
    for field, value in changes.items():
        setattr(item, field, value)
    # The serializer gives early feedback; this check protects the invariant under the row lock.
    if not has_positive_macros(
        calories=item.calories, protein_g=item.protein_g, fiber_g=item.fiber_g
    ):
        raise ValueError(POSITIVE_MACROS_ERROR)
    item.save(update_fields=tuple(changes))
    recalculate_entry_totals(entry)
    return item


@transaction.atomic
def delete_entry_item(*, user: User, entry_id: int, item_id: int) -> None:
    entry = _locked_entry(user=user, entry_id=entry_id)
    item = FoodItem.objects.get(pk=item_id, entry=entry)
    if entry.items.count() == 1:
        raise EntryRequiresOneItem
    item.delete()
    recalculate_entry_totals(entry)
