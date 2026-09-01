from datetime import UTC, datetime
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from ai.exceptions import FoodAnalysisQuotaExceeded

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="analysis@example.com", timezone="UTC")


def test_analysis_requires_authentication(db):
    response = APIClient().post(
        "/api/analyses/", {"photo_key": "pending/1/meal.jpg"}, format="json"
    )
    assert response.status_code == 401


def test_analysis_rejects_another_users_pending_key(user):
    client = APIClient()
    client.force_authenticate(user)

    response = client.post("/api/analyses/", {"photo_key": "pending/999/meal.jpg"}, format="json")

    assert response.status_code == 400


def test_analysis_returns_validated_items(user):
    client = APIClient()
    client.force_authenticate(user)
    result = {
        "analysis_id": 7,
        "calories": "540.00",
        "protein_g": "41.00",
        "fiber_g": "8.00",
        "items": [
            {
                "name": "Chicken",
                "portion": "2 pieces",
                "calories": "540.00",
                "protein_g": "41.00",
                "fiber_g": "8.00",
            }
        ],
    }
    with mock.patch("ai.views.create_food_analysis", return_value=result) as create:
        response = client.post(
            "/api/analyses/",
            {"photo_key": f"pending/{user.pk}/meal.jpg", "description": "two thighs"},
            format="json",
        )

    assert response.status_code == 201
    assert response.data == result
    create.assert_called_once_with(
        user=user,
        photo_key=f"pending/{user.pk}/meal.jpg",
        description="two thighs",
    )


def test_analysis_maps_the_rolling_quota(user):
    client = APIClient()
    client.force_authenticate(user)
    error = FoodAnalysisQuotaExceeded(
        limit=500,
        used=500,
        retry_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    with mock.patch("ai.views.create_food_analysis", side_effect=error):
        response = client.post(
            "/api/analyses/", {"photo_key": f"pending/{user.pk}/meal.jpg"}, format="json"
        )

    assert response.status_code == 429
    assert response.data["code"] == "food_analysis_quota_exceeded"
    assert response.data["limit"] == 500
    assert response.data["used"] == 500
