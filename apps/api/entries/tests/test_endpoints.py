from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from entries.models import DailyLog, FoodEntry, FoodItem
from entries.services import ManualItem, create_manual_entry
from targets.models import TargetVersion

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def payload(**item_overrides):
    item = {
        "name": "Greek yogurt",
        "quantity": "1.50",
        "calories": "120.00",
        "protein_g": "18.00",
        "fiber_g": "2.00",
        **item_overrides,
    }
    return {
        "local_date": "2026-08-31",
        "timezone": "America/New_York",
        "eaten_at": datetime(2026, 8, 31, 16, 30, tzinfo=UTC).isoformat(),
        "item": item,
    }


@pytest.mark.django_db
def test_manual_save_creates_one_item_and_derived_totals():
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    response = client_for(user).post(reverse("entry-list"), payload(), format="json")

    assert response.status_code == 201
    entry = FoodEntry.objects.get()
    assert entry.source == "manual"
    assert entry.calories == Decimal("180.00")
    assert entry.protein_g == Decimal("27.00")
    assert entry.fiber_g == Decimal("3.00")
    assert FoodItem.objects.get(entry=entry).name == "Greek yogurt"


@pytest.mark.django_db
def test_day_read_returns_totals_and_never_exposes_another_user():
    owner = User.objects.create_user(email="owner@example.com", timezone="America/New_York")
    other = User.objects.create_user(email="other@example.com", timezone="America/New_York")
    client_for(owner).post(reverse("entry-list"), payload(), format="json")

    owner_day = client_for(owner).get(reverse("day-detail", args=["2026-08-31"]))
    other_day = client_for(other).get(reverse("day-detail", args=["2026-08-31"]))

    assert owner_day.data["calories"] == "180.00"
    assert [entry["description"] for entry in owner_day.data["entries"]] == ["Greek yogurt"]
    assert other_day.data["entries"] == []
    assert DailyLog.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "0"},
        {"calories": "-1"},
        {"calories": "0", "protein_g": "0", "fiber_g": "0"},
        {"name": ""},
    ],
)
def test_manual_save_rejects_invalid_items(change):
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    response = client_for(user).post(reverse("entry-list"), payload(**change), format="json")
    assert response.status_code == 400
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
def test_manual_save_requires_the_synchronized_timezone():
    user = User.objects.create_user(email="alex@example.com", timezone="UTC")
    response = client_for(user).post(reverse("entry-list"), payload(), format="json")
    assert response.status_code == 400
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
def test_manual_save_rejects_an_invalid_stored_timezone_instead_of_raising():
    user = User.objects.create_user(email="alex@example.com", timezone="Not/A-Timezone")
    invalid = payload()
    invalid["timezone"] = "Not/A-Timezone"

    response = client_for(user).post(reverse("entry-list"), invalid, format="json")

    assert response.status_code == 400
    assert response.data["timezone"] == ["Synchronize the device timezone and try again."]
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
def test_manual_save_requires_authentication():
    response = APIClient().post(reverse("entry-list"), payload(), format="json")

    assert response.status_code == 401
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
def test_day_read_requires_authentication():
    response = APIClient().get(reverse("day-detail", args=["2026-08-31"]))

    assert response.status_code == 401


@pytest.mark.django_db
def test_manual_save_rejects_an_eaten_time_from_another_local_date():
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    invalid = payload()
    invalid["eaten_at"] = datetime(2026, 9, 1, 16, 30, tzinfo=UTC).isoformat()

    response = client_for(user).post(reverse("entry-list"), invalid, format="json")

    assert response.status_code == 400
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("local_date", ["20260831", "2026-02-30", "not-a-date"])
def test_day_read_rejects_invalid_date_formats(local_date):
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")

    response = client_for(user).get(reverse("day-detail", args=[local_date]))

    assert response.status_code == 400
    assert response.data == {"local_date": ["Enter a date in YYYY-MM-DD format."]}


@pytest.mark.django_db
def test_day_captures_the_target_effective_on_its_first_entry():
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    old_target = TargetVersion.objects.create(
        user=user,
        calories=2000,
        protein_g=150,
        fiber_g=25,
        source=TargetVersion.Source.MANUAL,
        effective_from=date(2026, 8, 1),
    )
    TargetVersion.objects.create(
        user=user,
        calories=2200,
        protein_g=170,
        fiber_g=30,
        source=TargetVersion.Source.MANUAL,
        effective_from=date(2026, 9, 1),
    )

    response = client_for(user).post(reverse("entry-list"), payload(), format="json")

    assert response.status_code == 201
    assert DailyLog.objects.get().target_version == old_target

    TargetVersion.objects.create(
        user=user,
        calories=2100,
        protein_g=160,
        fiber_g=28,
        source=TargetVersion.Source.MANUAL,
        effective_from=date(2026, 8, 31),
    )
    day = client_for(user).get(reverse("day-detail", args=["2026-08-31"]))
    assert day.data["targets"]["calories"] == 2000


@pytest.mark.django_db
def test_empty_day_reads_effective_targets_without_creating_a_log():
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    TargetVersion.objects.create(
        user=user,
        calories=2000,
        protein_g=150,
        fiber_g=25,
        source=TargetVersion.Source.MANUAL,
        effective_from=date(2026, 8, 1),
    )

    response = client_for(user).get(reverse("day-detail", args=["2026-08-31"]))

    assert response.status_code == 200
    assert response.data["targets"] == {"calories": 2000, "protein_g": 150, "fiber_g": 25}
    assert DailyLog.objects.count() == 0


@pytest.mark.django_db
def test_day_read_orders_entries_newest_first():
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    first = payload(name="Breakfast")
    first["eaten_at"] = datetime(2026, 8, 31, 12, 0, tzinfo=UTC).isoformat()
    second = payload(name="Dinner")
    second["eaten_at"] = datetime(2026, 8, 31, 22, 0, tzinfo=UTC).isoformat()
    client = client_for(user)
    client.post(reverse("entry-list"), first, format="json")
    client.post(reverse("entry-list"), second, format="json")

    response = client.get(reverse("day-detail", args=["2026-08-31"]))

    assert [entry["description"] for entry in response.data["entries"]] == [
        "Dinner",
        "Breakfast",
    ]


@pytest.mark.django_db
def test_manual_save_rolls_back_the_day_and_entry_when_the_item_write_fails():
    user = User.objects.create_user(email="alex@example.com", timezone="America/New_York")
    item = ManualItem(
        name="Greek yogurt",
        quantity=Decimal("1"),
        calories=Decimal("120"),
        protein_g=Decimal("18"),
        fiber_g=Decimal("2"),
    )

    with patch(
        "entries.services.FoodItem.objects.create", side_effect=RuntimeError("write failed")
    ):
        with pytest.raises(RuntimeError, match="write failed"):
            create_manual_entry(
                user=user,
                local_date=date(2026, 8, 31),
                eaten_at=datetime(2026, 8, 31, 16, 30, tzinfo=UTC),
                item=item,
            )

    assert DailyLog.objects.count() == 0
    assert FoodEntry.objects.count() == 0
