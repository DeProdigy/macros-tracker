from datetime import UTC, date, datetime
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from ai.models import FoodAnalysisCall
from entries.models import FoodEntry
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
