from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from entries.models import DailyLog, FoodEntry, FoodItem

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
