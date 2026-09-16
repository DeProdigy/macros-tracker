import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model

from ai.models import FoodAnalysisCall
from ai.provider import ProviderFoodAnalysis, ProviderOutputError, ProviderResult
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


def test_provider_schema_declares_one_type_per_field():
    """OpenAI compiles this schema into a decoder grammar before it generates.

    A `Decimal` field makes pydantic emit a two-branch union of a number and a
    patterned string, and that pattern holds a negative lookahead. The compile
    step rejects the shape, the call returns `status=incomplete` with
    `reason=max_output_tokens`, and usage reports zero tokens in and zero out.
    The reported reason names the symptom, not the cause, so raising the token
    budget does nothing.

    The assertion walks the property definitions rather than searching the
    serialised schema for a keyword. A keyword search also matches prose, which
    the second assertion here exists to keep out.

    This test only proves the shape that broke it is gone. It cannot prove OpenAI
    accepts the schema, because it never calls OpenAI. A live call is the only
    proof of that, and a live call costs money on every run.
    """
    schema = ProviderFoodAnalysis.model_json_schema()
    definitions = [schema, *schema.get("$defs", {}).values()]

    unions = [
        f"{definition.get('title')}.{field}"
        for definition in definitions
        for field, spec in definition.get("properties", {}).items()
        if "anyOf" in spec or "oneOf" in spec
    ]

    assert unions == []


def test_provider_schema_carries_no_prose():
    """A class docstring here would be sent to OpenAI on every analysis call.

    Pydantic copies a class docstring into the schema's `description`, and the
    SDK puts the whole schema in the request body. Engineering notes would then
    be billed as input tokens and read by the model as instructions about the
    task. Explain this model in a comment above the class instead.

    An 896-character docstring once made up more than half of this schema.
    """
    schema = json.dumps(ProviderFoodAnalysis.model_json_schema())

    assert "description" not in schema
