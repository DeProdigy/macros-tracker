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


def create_item(
    user,
    *,
    name="Greek yogurt",
    portion_label="1 cup",
    eaten_at=datetime(2026, 9, 14, 16, tzinfo=UTC),
    calories="120.00",
    protein_g="18.00",
    fiber_g="2.00",
):
    day, _ = DailyLog.objects.get_or_create(user=user, local_date=eaten_at.date())
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.MANUAL,
        description=name,
        eaten_at=eaten_at,
        calories=0,
        protein_g=0,
        fiber_g=0,
    )
    item = FoodItem.objects.create(
        entry=entry,
        name=name,
        portion_label=portion_label,
        quantity=1,
        calories=Decimal(calories),
        protein_g=Decimal(protein_g),
        fiber_g=Decimal(fiber_g),
    )
    recalculate_entry_totals(entry)
    return item


def recent_payload(item_id, **overrides):
    return {
        "local_date": "2026-09-15",
        "timezone": "America/New_York",
        "eaten_at": datetime(2026, 9, 15, 16, 30, tzinfo=UTC).isoformat(),
        "recent_item_id": item_id,
        "quantity": "1.50",
        **overrides,
    }


@pytest.mark.django_db
def test_food_list_is_distinct_by_normalized_name_and_portion_with_latest_macros():
    user = User.objects.create_user(email="recents@example.com", timezone="America/New_York")
    other = User.objects.create_user(email="other@example.com", timezone="America/New_York")
    create_item(
        user,
        name=" Greek Yogurt ",
        portion_label=" 1 CUP ",
        eaten_at=datetime(2026, 9, 12, 16, tzinfo=UTC),
        calories="100.00",
    )
    latest = create_item(
        user,
        name="greek yogurt",
        portion_label="1 cup",
        eaten_at=datetime(2026, 9, 14, 16, tzinfo=UTC),
        calories="120.00",
    )
    other_portion = create_item(
        user,
        name="Greek yogurt",
        portion_label="single pot",
        eaten_at=datetime(2026, 9, 13, 16, tzinfo=UTC),
        calories="90.00",
    )
    create_item(
        other,
        name="Private food",
        eaten_at=datetime(2026, 9, 15, 16, tzinfo=UTC),
    )

    response = client_for(user).get(reverse("food-list"))

    assert response.status_code == 200
    assert [food["id"] for food in response.data] == [latest.pk, other_portion.pk]
    assert response.data[0]["calories"] == "120.00"
    assert [food["portion_label"] for food in response.data] == ["1 cup", "single pot"]


@pytest.mark.django_db
@pytest.mark.parametrize("search", ["YOGURT", "CuP"])
def test_food_list_searches_name_and_portion_case_insensitively(search):
    user = User.objects.create_user(email="search@example.com", timezone="UTC")
    matching = create_item(user)
    create_item(user, name="Avocado", portion_label="half")

    response = client_for(user).get(reverse("food-list"), {"search": search})

    assert response.status_code == 200
    assert [food["id"] for food in response.data] == [matching.pk]


@pytest.mark.django_db
def test_food_list_requires_authentication():
    response = APIClient().get(reverse("food-list"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_food_list_returns_at_most_one_hundred_distinct_items():
    user = User.objects.create_user(email="limited@example.com", timezone="UTC")
    for index in range(101):
        create_item(user, name=f"Food {index}")

    response = client_for(user).get(reverse("food-list"))

    assert response.status_code == 200
    assert len(response.data) == 100
    assert response.data[0]["name"] == "Food 100"
    assert response.data[-1]["name"] == "Food 1"


@pytest.mark.django_db
def test_recent_save_copies_the_item_into_a_new_entry_without_ai_or_photo_storage():
    user = User.objects.create_user(email="relog@example.com", timezone="America/New_York")
    source = create_item(user)
    source_values = {
        "name": source.name,
        "portion_label": source.portion_label,
        "quantity": source.quantity,
        "calories": source.calories,
        "protein_g": source.protein_g,
        "fiber_g": source.fiber_g,
    }

    with patch("entries.services.copy_analysis_object_to_entry") as copy_photo:
        response = client_for(user).post(
            reverse("entry-list"), recent_payload(source.pk), format="json"
        )

    assert response.status_code == 201
    assert response.data["source"] == "recent"
    assert response.data["photo_url"] is None
    assert response.data["calories"] == "180.00"
    assert response.data["protein_g"] == "27.00"
    assert response.data["fiber_g"] == "3.00"
    copy_photo.assert_not_called()

    entry = FoodEntry.objects.get(source=FoodEntry.Source.RECENT)
    assert entry.eaten_at == datetime(2026, 9, 15, 16, 30, tzinfo=UTC)
    copied = entry.items.get()
    assert copied.pk != source.pk
    assert copied.quantity == Decimal("1.50")
    assert {
        "name": copied.name,
        "portion_label": copied.portion_label,
        "calories": copied.calories,
        "protein_g": copied.protein_g,
        "fiber_g": copied.fiber_g,
    } == {key: value for key, value in source_values.items() if key != "quantity"}
    source.refresh_from_db()
    assert {
        "name": source.name,
        "portion_label": source.portion_label,
        "quantity": source.quantity,
        "calories": source.calories,
        "protein_g": source.protein_g,
        "fiber_g": source.fiber_g,
    } == source_values


@pytest.mark.django_db
def test_recent_save_hides_another_users_item():
    owner = User.objects.create_user(email="owner@example.com", timezone="America/New_York")
    attacker = User.objects.create_user(email="attacker@example.com", timezone="America/New_York")
    source = create_item(owner)

    response = client_for(attacker).post(
        reverse("entry-list"), recent_payload(source.pk), format="json"
    )

    assert response.status_code == 400
    assert response.data["recent_item_id"] == ["Choose a food from your Recents."]
    assert FoodEntry.objects.count() == 1


@pytest.mark.django_db
def test_recent_save_rejects_invalid_quantity_and_local_timing():
    user = User.objects.create_user(email="invalid@example.com", timezone="America/New_York")
    source = create_item(user)
    client = client_for(user)

    invalid_quantity = client.post(
        reverse("entry-list"), recent_payload(source.pk, quantity="0"), format="json"
    )
    invalid_date = client.post(
        reverse("entry-list"),
        recent_payload(source.pk, local_date="2026-09-14"),
        format="json",
    )

    assert invalid_quantity.status_code == 400
    assert invalid_date.status_code == 400
    assert FoodEntry.objects.count() == 1


@pytest.mark.django_db
def test_recent_save_rejects_a_quantity_that_overflows_entry_totals():
    user = User.objects.create_user(email="overflow@example.com", timezone="America/New_York")
    source = create_item(user)

    response = client_for(user).post(
        reverse("entry-list"),
        recent_payload(source.pk, quantity="999999.99"),
        format="json",
    )

    assert response.status_code == 400
    assert response.data["quantity"] == ["Quantity makes macro totals too large."]
    assert FoodEntry.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("extra_source", [{"item": {}}, {"analysis_id": 1}])
def test_recent_save_rejects_mixed_entry_sources(extra_source):
    user = User.objects.create_user(email="mixed@example.com", timezone="America/New_York")
    source = create_item(user)

    response = client_for(user).post(
        reverse("entry-list"),
        recent_payload(source.pk, **extra_source),
        format="json",
    )

    assert response.status_code == 400
    assert response.data["non_field_errors"] == ["Provide exactly one entry source."]
    assert FoodEntry.objects.count() == 1


@pytest.mark.django_db
def test_recent_save_rolls_back_when_copying_the_item_fails():
    user = User.objects.create_user(email="rollback@example.com", timezone="America/New_York")
    source = create_item(user)

    with (
        patch("entries.services.FoodItem.objects.create", side_effect=RuntimeError("failed copy")),
        pytest.raises(RuntimeError, match="failed copy"),
    ):
        client_for(user).post(reverse("entry-list"), recent_payload(source.pk), format="json")

    assert FoodEntry.objects.count() == 1
    assert DailyLog.objects.filter(local_date=date(2026, 9, 15)).count() == 0
