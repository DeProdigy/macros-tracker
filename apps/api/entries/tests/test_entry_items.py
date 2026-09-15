from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from entries.models import DailyLog, FoodEntry, FoodItem
from entries.services import recalculate_entry_totals

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def create_entry(user, *, item_count=1):
    day = DailyLog.objects.create(user=user, local_date=date(2026, 9, 1))
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.MANUAL,
        description="Lunch",
        eaten_at=datetime(2026, 9, 1, 17, tzinfo=UTC),
        calories=0,
        protein_g=0,
        fiber_g=0,
    )
    items = [
        FoodItem.objects.create(
            entry=entry,
            name=f"Item {index}",
            portion_label="1 serving",
            quantity=1,
            calories=100,
            protein_g=10,
            fiber_g=2,
        )
        for index in range(item_count)
    ]
    recalculate_entry_totals(entry)
    return entry, items


def item_payload(**overrides):
    return {
        "name": "Avocado",
        "portion_label": "half",
        "quantity": "1.50",
        "calories": "120.00",
        "protein_g": "2.00",
        "fiber_g": "5.00",
        **overrides,
    }


@pytest.mark.django_db
def test_add_item_recalculates_entry_and_day_totals():
    user = User.objects.create_user(email="add-item@example.com", timezone="UTC")
    entry, _ = create_entry(user)

    response = client_for(user).post(
        reverse("entry-item-list", args=[entry.pk]), item_payload(), format="json"
    )

    assert response.status_code == 201
    entry.refresh_from_db()
    assert entry.calories == Decimal("280.00")
    assert entry.protein_g == Decimal("13.00")
    assert entry.fiber_g == Decimal("9.50")
    day = client_for(user).get(reverse("day-detail", args=["2026-09-01"]))
    assert day.data["calories"] == "280.00"
    assert day.data["fiber_g"] == "9.50"


@pytest.mark.django_db
def test_patch_item_changes_fields_and_quantity_adjusted_totals():
    user = User.objects.create_user(email="patch-item@example.com", timezone="UTC")
    entry, items = create_entry(user)

    response = client_for(user).patch(
        reverse("entry-item-detail", args=[entry.pk, items[0].pk]),
        {
            "name": "Greek yogurt",
            "portion_label": "1 cup",
            "quantity": "2.50",
            "calories": "80.00",
            "protein_g": "12.00",
            "fiber_g": "1.00",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == "Greek yogurt"
    entry.refresh_from_db()
    assert entry.calories == Decimal("200.00")
    assert entry.protein_g == Decimal("30.00")
    assert entry.fiber_g == Decimal("2.50")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": "0"},
        {"calories": "-1"},
        {"calories": "0", "protein_g": "0", "fiber_g": "0"},
        {"name": ""},
        {},
    ],
)
def test_patch_item_rejects_invalid_changes(changes):
    user = User.objects.create_user(email="invalid-item@example.com", timezone="UTC")
    entry, items = create_entry(user)

    response = client_for(user).patch(
        reverse("entry-item-detail", args=[entry.pk, items[0].pk]), changes, format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_delete_item_recalculates_totals_but_rejects_deleting_the_last_item():
    user = User.objects.create_user(email="delete-item@example.com", timezone="UTC")
    entry, items = create_entry(user, item_count=2)
    client = client_for(user)

    deleted = client.delete(reverse("entry-item-detail", args=[entry.pk, items[0].pk]))

    assert deleted.status_code == 204
    entry.refresh_from_db()
    assert entry.calories == Decimal("100.00")
    blocked = client.delete(reverse("entry-item-detail", args=[entry.pk, items[1].pk]))
    assert blocked.status_code == 409
    assert blocked.data["code"] == "entry_requires_one_item"
    assert FoodItem.objects.filter(entry=entry).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_item_writes_hide_another_users_entry(method):
    owner = User.objects.create_user(email="item-owner@example.com", timezone="UTC")
    attacker = User.objects.create_user(email="item-attacker@example.com", timezone="UTC")
    entry, items = create_entry(owner)
    client = client_for(attacker)
    if method == "post":
        response = client.post(
            reverse("entry-item-list", args=[entry.pk]), item_payload(), format="json"
        )
    else:
        response = getattr(client, method)(
            reverse("entry-item-detail", args=[entry.pk, items[0].pk]),
            {"quantity": "2.00"} if method == "patch" else None,
            format="json",
        )

    assert response.status_code == 404


@pytest.mark.django_db
def test_failed_recalculation_rolls_back_the_item_change():
    user = User.objects.create_user(email="rollback-item@example.com", timezone="UTC")
    entry, items = create_entry(user)
    client = client_for(user)

    with (
        patch(
            "entries.services.recalculate_entry_totals", side_effect=RuntimeError("failed totals")
        ),
        pytest.raises(RuntimeError, match="failed totals"),
    ):
        client.patch(
            reverse("entry-item-detail", args=[entry.pk, items[0].pk]),
            {"quantity": "2.00"},
            format="json",
        )

    entry.refresh_from_db()
    items[0].refresh_from_db()
    assert entry.calories == Decimal("100.00")
    assert items[0].quantity == Decimal("1.00")
