from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from ai.models import FoodAnalysisCall
from ai.provider import ProviderOutputError, ProviderResult
from ai.services import create_food_analysis

User = get_user_model()


@pytest.mark.django_db
def test_service_retains_photo_and_records_validated_provider_result():
    user = User.objects.create_user(email="service@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={
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
            ]
        },
        provider_request_id="resp_123",
        model="gpt-5-mini-2026-08-01",
        input_tokens=1000,
        output_tokens=200,
        usage={"input_tokens": 1000, "output_tokens": 200},
    )
    pending = f"pending/{user.pk}/meal.jpg"
    retained = f"analyses/{user.pk}/meal.jpg"
    with (
        mock.patch("uploads.services.retain_analysis_object", return_value=retained),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider) as analyze,
    ):
        result = create_food_analysis(user=user, photo_key=pending, description="two thighs")

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.SUCCEEDED
    assert call.request_payload == {"photo_key": retained, "description": "two thighs"}
    assert "https://" not in str(call.request_payload)
    assert call.response_payload == result
    assert result["calories"] == "540.00"
    assert len(result["items"]) == 2
    analyze.assert_called_once_with(image_url="https://signed.invalid", description="two thighs")


@pytest.mark.django_db
def test_service_rounds_three_decimal_provider_values_before_recording_success():
    user = User.objects.create_user(email="rounding@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={
            "items": [
                {
                    "name": "Yogurt",
                    "portion": "1 cup",
                    "calories": "123.456",
                    "protein_g": "10.005",
                    "fiber_g": "0.333",
                }
            ]
        },
        provider_request_id="resp_rounding",
        model="gpt-5-mini-2026-08-01",
        input_tokens=100,
        output_tokens=50,
        usage={"input_tokens": 100, "output_tokens": 50},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/meal.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
    ):
        result = create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/meal.jpg",
            description="",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.SUCCEEDED
    assert result["items"][0]["calories"] == "123.46"
    assert result["items"][0]["protein_g"] == "10.01"
    assert result["items"][0]["fiber_g"] == "0.33"
    assert result["calories"] == "123.46"
    assert call.response_payload == result


@pytest.mark.django_db
def test_incomplete_provider_output_keeps_usage_and_failure_details():
    user = User.objects.create_user(email="incomplete@example.com", timezone="UTC")
    error = ProviderOutputError(
        payload={
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [],
        },
        raw_response="",
        provider_request_id="resp_incomplete",
        input_tokens=900,
        output_tokens=2048,
        usage={"input_tokens": 900, "output_tokens": 2048},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/meal.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", side_effect=error),
        pytest.raises(ProviderOutputError),
    ):
        create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/meal.jpg",
            description="",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.failure_category == "invalid_model_output"
    assert call.response_payload is not None
    assert call.response_payload["incomplete_details"]["reason"] == "max_output_tokens"
    assert call.provider_request_id == "resp_incomplete"
    assert call.output_tokens == 2048
    assert call.quota_debited_at is not None


@pytest.mark.django_db
def test_internal_provider_type_error_keeps_provider_failure_category():
    user = User.objects.create_user(email="provider-bug@example.com", timezone="UTC")
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/meal.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", side_effect=TypeError("provider bug")),
        pytest.raises(TypeError, match="provider bug"),
    ):
        create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/meal.jpg",
            description="",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.failure_category == "provider_failure"
    assert call.quota_debited_at is None
