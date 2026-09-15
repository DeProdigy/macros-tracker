from datetime import UTC, date, datetime
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from ai.models import FoodAnalysisCall
from entries.models import DailyLog, FoodEntry
from entries.services import create_photo_entry

User = get_user_model()


@pytest.mark.django_db
def test_photo_save_creates_one_entry_with_multiple_items():
    user = User.objects.create_user(email="photo@example.com", timezone="UTC")
    call = FoodAnalysisCall.objects.create(
        user=user,
        status=FoodAnalysisCall.Status.SUCCEEDED,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        request_payload={
            "photo_key": f"analyses/{user.pk}/meal.jpg",
            "description": "lunch",
        },
        response_payload={
            "analysis_id": 1,
            "calories": "540.00",
            "protein_g": "41.00",
            "fiber_g": "8.00",
            "items": [
                {
                    "name": "Chicken",
                    "portion": "2 pieces",
                    "calories": "360.00",
                    "protein_g": "38.00",
                    "fiber_g": "0.00",
                },
                {
                    "name": "Broccoli",
                    "portion": "1 cup",
                    "calories": "180.00",
                    "protein_g": "3.00",
                    "fiber_g": "8.00",
                },
            ],
        },
    )
    entry_key = f"entries/{user.pk}/meal.jpg"
    with (
        mock.patch("entries.services.copy_analysis_object_to_entry", return_value=entry_key),
        mock.patch("entries.services.delete_object") as delete,
    ):
        entry = create_photo_entry(
            user=user,
            local_date=date(2026, 9, 1),
            eaten_at=datetime(2026, 9, 1, 17, tzinfo=UTC),
            analysis_id=call.pk,
        )

    entry.refresh_from_db()
    call.refresh_from_db()
    assert entry.source == FoodEntry.Source.PHOTO
    assert entry.photo_key == entry_key
    assert entry.analysis_call == call
    assert entry.items.count() == 2
    assert str(entry.calories) == "540.00"
    assert call.request_payload["photo_key"] == entry_key
    delete.assert_called_once_with(key=f"analyses/{user.pk}/meal.jpg")


@pytest.mark.django_db
def test_photo_save_uses_corrected_items_without_changing_the_analysis_response():
    user = User.objects.create_user(email="corrected-photo@example.com", timezone="UTC")
    original_response = {
        "analysis_id": 1,
        "calories": "360.00",
        "protein_g": "38.00",
        "fiber_g": "0.00",
        "items": [
            {
                "name": "Chicken",
                "portion": "2 pieces",
                "calories": "360.00",
                "protein_g": "38.00",
                "fiber_g": "0.00",
            }
        ],
    }
    call = FoodAnalysisCall.objects.create(
        user=user,
        status=FoodAnalysisCall.Status.SUCCEEDED,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        request_payload={
            "photo_key": f"analyses/{user.pk}/meal.jpg",
            "description": "lunch",
        },
        response_payload=original_response,
    )
    client = APIClient()
    client.force_authenticate(user)
    with (
        mock.patch(
            "entries.services.copy_analysis_object_to_entry",
            return_value=f"entries/{user.pk}/meal.jpg",
        ),
        mock.patch("entries.services.delete_object"),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
    ):
        response = client.post(
            "/api/entries/",
            {
                "local_date": "2026-09-01",
                "timezone": "UTC",
                "eaten_at": "2026-09-01T17:00:00Z",
                "analysis_id": call.pk,
                "items": [
                    {
                        "name": "Chicken thigh",
                        "portion_label": "1 piece",
                        "quantity": "2.00",
                        "calories": "190.00",
                        "protein_g": "20.00",
                        "fiber_g": "0.00",
                    }
                ],
            },
            format="json",
        )

    assert response.status_code == 201
    entry = FoodEntry.objects.get()
    entry.refresh_from_db()
    call.refresh_from_db()
    assert entry.calories == Decimal("380.00")
    assert entry.protein_g == Decimal("40.00")
    assert entry.items.get().name == "Chicken thigh"
    assert call.response_payload == original_response


@pytest.mark.django_db
def test_photo_save_rejects_an_empty_corrected_item_list():
    user = User.objects.create_user(email="empty-corrections@example.com", timezone="UTC")
    call = FoodAnalysisCall.objects.create(
        user=user,
        status=FoodAnalysisCall.Status.SUCCEEDED,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        request_payload={"photo_key": f"analyses/{user.pk}/meal.jpg", "description": ""},
        response_payload={
            "items": [
                {
                    "name": "Chicken",
                    "portion": "1 piece",
                    "calories": "190.00",
                    "protein_g": "20.00",
                    "fiber_g": "0.00",
                }
            ]
        },
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/entries/",
        {
            "local_date": "2026-09-01",
            "timezone": "UTC",
            "eaten_at": "2026-09-01T17:00:00Z",
            "analysis_id": call.pk,
            "items": [],
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["items"]
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
def test_photo_save_rejects_another_users_analysis():
    owner = User.objects.create_user(email="owner@example.com", timezone="UTC")
    attacker = User.objects.create_user(email="attacker@example.com", timezone="UTC")
    call = FoodAnalysisCall.objects.create(
        user=owner,
        status=FoodAnalysisCall.Status.SUCCEEDED,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        request_payload={"photo_key": f"analyses/{owner.pk}/meal.jpg", "description": ""},
        response_payload={"items": []},
    )
    client = APIClient()
    client.force_authenticate(attacker)

    response = client.post(
        "/api/entries/",
        {
            "local_date": "2026-09-01",
            "timezone": "UTC",
            "eaten_at": "2026-09-01T17:00:00Z",
            "analysis_id": call.pk,
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["analysis_id"]
    assert FoodEntry.objects.count() == 0


@pytest.mark.django_db
def test_failed_duplicate_save_does_not_delete_committed_entry_photo():
    user = User.objects.create_user(email="duplicate@example.com", timezone="UTC")
    call = FoodAnalysisCall.objects.create(
        user=user,
        status=FoodAnalysisCall.Status.SUCCEEDED,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        request_payload={"photo_key": f"analyses/{user.pk}/meal.jpg", "description": ""},
        response_payload={"items": []},
    )
    day = DailyLog.objects.create(user=user, local_date=date(2026, 9, 1))
    entry_key = f"entries/{user.pk}/meal.jpg"
    FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.PHOTO,
        description="Meal",
        eaten_at=datetime(2026, 9, 1, 17, tzinfo=UTC),
        calories="1.00",
        protein_g="1.00",
        fiber_g="1.00",
        photo_key=entry_key,
        analysis_call=call,
    )

    with (
        mock.patch("entries.services.copy_analysis_object_to_entry", return_value=entry_key),
        mock.patch("entries.services._store_photo_entry", side_effect=ValueError("saved")),
        mock.patch("entries.services.delete_object") as delete,
        pytest.raises(ValueError, match="saved"),
    ):
        create_photo_entry(
            user=user,
            local_date=date(2026, 9, 1),
            eaten_at=datetime(2026, 9, 1, 17, tzinfo=UTC),
            analysis_id=call.pk,
        )

    delete.assert_not_called()


@pytest.mark.django_db
def test_missing_analysis_source_after_concurrent_save_reports_already_saved():
    user = User.objects.create_user(email="stale-copy@example.com", timezone="UTC")
    call = FoodAnalysisCall.objects.create(
        user=user,
        status=FoodAnalysisCall.Status.SUCCEEDED,
        started_at=datetime(2026, 9, 1, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, tzinfo=UTC),
        request_payload={"photo_key": f"analyses/{user.pk}/meal.jpg", "description": ""},
        response_payload={"items": []},
    )
    day = DailyLog.objects.create(user=user, local_date=date(2026, 9, 1))
    FoodEntry.objects.create(
        daily_log=day,
        source=FoodEntry.Source.PHOTO,
        description="Meal",
        eaten_at=datetime(2026, 9, 1, 17, tzinfo=UTC),
        calories="1.00",
        protein_g="1.00",
        fiber_g="1.00",
        photo_key=f"entries/{user.pk}/meal.jpg",
        analysis_call=call,
    )

    with (
        mock.patch(
            "entries.services.copy_analysis_object_to_entry",
            side_effect=RuntimeError("source disappeared"),
        ),
        pytest.raises(ValueError, match="already saved"),
    ):
        create_photo_entry(
            user=user,
            local_date=date(2026, 9, 1),
            eaten_at=datetime(2026, 9, 1, 17, tzinfo=UTC),
            analysis_id=call.pk,
        )
