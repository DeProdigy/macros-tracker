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


def create_entry(
    user,
    *,
    local_date=date(2026, 9, 14),
    eaten_at=datetime(2026, 9, 14, 16, tzinfo=UTC),
    description="Lunch",
    photo_key="",
    item_names=("Chicken", "Rice"),
):
    day, _ = DailyLog.objects.get_or_create(user=user, local_date=local_date)
    entry = FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.PHOTO if photo_key else FoodEntry.Source.MANUAL,
        description=description,
        eaten_at=eaten_at,
        calories=0,
        protein_g=0,
        fiber_g=0,
        photo_key=photo_key,
    )
    for index, name in enumerate(item_names, start=1):
        FoodItem.objects.create(
            entry=entry,
            name=name,
            portion_label="1 serving",
            quantity=Decimal(index),
            calories=Decimal("100.00"),
            protein_g=Decimal("10.00"),
            fiber_g=Decimal("2.00"),
        )
    return recalculate_entry_totals(entry)


def copy_payload(source_entry_id, **overrides):
    return {
        "local_date": "2026-09-15",
        "timezone": "America/New_York",
        "eaten_at": datetime(2026, 9, 15, 16, 30, tzinfo=UTC).isoformat(),
        "source_entry_id": source_entry_id,
        **overrides,
    }


@pytest.mark.django_db
def test_entry_detail_returns_one_owned_entry_with_a_retained_photo():
    user = User.objects.create_user(email="detail@example.com", timezone="America/New_York")
    entry = create_entry(user, photo_key=f"entries/{user.pk}/meal.jpg")

    with patch("uploads.services.presign_download", return_value="https://signed.invalid/meal"):
        response = client_for(user).get(reverse("entry-detail", args=[entry.pk]))

    assert response.status_code == 200
    assert response.data["id"] == entry.pk
    assert response.data["photo_url"] == "https://signed.invalid/meal"
    assert [item["name"] for item in response.data["items"]] == ["Chicken", "Rice"]


@pytest.mark.django_db
def test_entry_detail_hides_another_users_entry_from_read_and_delete():
    owner = User.objects.create_user(email="detail-owner@example.com", timezone="UTC")
    other = User.objects.create_user(email="detail-other@example.com", timezone="UTC")
    entry = create_entry(owner)
    client = client_for(other)

    read_response = client.get(reverse("entry-detail", args=[entry.pk]))
    delete_response = client.delete(reverse("entry-detail", args=[entry.pk]))

    assert read_response.status_code == 404
    assert delete_response.status_code == 404
    assert FoodEntry.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
def test_whole_entry_relog_copies_items_without_photo_or_ai():
    user = User.objects.create_user(email="copy@example.com", timezone="America/New_York")
    source = create_entry(user, photo_key=f"entries/{user.pk}/meal.jpg")

    with (
        patch("entries.services.copy_analysis_object_to_entry") as copy_photo,
        patch("entries.services.delete_object") as delete_photo,
    ):
        response = client_for(user).post(
            reverse("entry-list"), copy_payload(source.pk), format="json"
        )

    assert response.status_code == 201
    assert response.data["source"] == "recent"
    assert response.data["photo_url"] is None
    assert response.data["eaten_at"] == "2026-09-15T16:30:00Z"
    assert response.data["calories"] == "300.00"
    copy_photo.assert_not_called()
    delete_photo.assert_not_called()

    copied = FoodEntry.objects.get(pk=response.data["id"])
    assert copied.photo_key == ""
    assert copied.analysis_call_id is None
    assert list(copied.items.values_list("name", "quantity")) == [
        ("Chicken", Decimal("1.00")),
        ("Rice", Decimal("2.00")),
    ]
    assert source.items.count() == 2


@pytest.mark.django_db
def test_whole_entry_relog_rejects_another_users_source():
    owner = User.objects.create_user(email="copy-owner@example.com", timezone="America/New_York")
    other = User.objects.create_user(email="copy-other@example.com", timezone="America/New_York")
    source = create_entry(owner)

    response = client_for(other).post(reverse("entry-list"), copy_payload(source.pk), format="json")

    assert response.status_code == 400
    assert response.data["source_entry_id"] == ["Choose an entry from your history."]
    assert FoodEntry.objects.count() == 1


@pytest.mark.django_db
def test_delete_entry_updates_day_totals_and_removes_an_unreferenced_photo(
    django_capture_on_commit_callbacks,
):
    user = User.objects.create_user(email="delete@example.com", timezone="UTC")
    photo_key = f"entries/{user.pk}/meal.jpg"
    entry = create_entry(user, photo_key=photo_key)

    with (
        patch("entries.services.delete_object") as delete_photo,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client_for(user).delete(reverse("entry-detail", args=[entry.pk]))

    assert response.status_code == 204
    assert not FoodEntry.objects.filter(pk=entry.pk).exists()
    delete_photo.assert_called_once_with(key=photo_key)
    day_response = client_for(user).get(reverse("day-detail", args=["2026-09-14"]))
    assert day_response.data["calories"] == "0.00"
    assert day_response.data["entries"] == []


@pytest.mark.django_db
def test_delete_entry_rechecks_photo_references_after_commit(
    django_capture_on_commit_callbacks,
):
    user = User.objects.create_user(email="shared-photo@example.com", timezone="UTC")
    photo_key = f"entries/{user.pk}/shared.jpg"
    first = create_entry(user, photo_key=photo_key, description="First")

    with (
        patch("entries.services.delete_object") as delete_photo,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client_for(user).delete(reverse("entry-detail", args=[first.pk]))
        second = create_entry(user, photo_key=photo_key, description="Second")

    assert response.status_code == 204
    assert FoodEntry.objects.filter(pk=second.pk, photo_key=photo_key).exists()
    delete_photo.assert_not_called()


@pytest.mark.django_db
def test_day_list_returns_only_owned_nonempty_days_in_the_requested_month():
    user = User.objects.create_user(email="days@example.com", timezone="UTC")
    other = User.objects.create_user(email="other-days@example.com", timezone="UTC")
    create_entry(user, local_date=date(2026, 9, 2), eaten_at=datetime(2026, 9, 2, 12, tzinfo=UTC))
    create_entry(user, local_date=date(2026, 9, 15), eaten_at=datetime(2026, 9, 15, 12, tzinfo=UTC))
    create_entry(user, local_date=date(2026, 8, 31), eaten_at=datetime(2026, 8, 31, 12, tzinfo=UTC))
    create_entry(
        other, local_date=date(2026, 9, 20), eaten_at=datetime(2026, 9, 20, 12, tzinfo=UTC)
    )
    DailyLog.objects.create(user=user, local_date=date(2026, 9, 25))

    response = client_for(user).get(reverse("day-list"), {"month": "2026-09"})

    assert response.status_code == 200
    assert response.data == [
        {"local_date": "2026-09-02"},
        {"local_date": "2026-09-15"},
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("month", ["202609", "2026-13", "9999-12", "not-a-month"])
def test_day_list_rejects_invalid_months(month):
    user = User.objects.create_user(email=f"{month}@example.com", timezone="UTC")

    response = client_for(user).get(reverse("day-list"), {"month": month})

    assert response.status_code == 400
    assert response.data == {"month": ["Enter a month in YYYY-MM format."]}
