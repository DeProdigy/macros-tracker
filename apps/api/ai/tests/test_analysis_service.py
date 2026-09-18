import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from ai.exceptions import FoodAnalysisNoFoodVisible
from ai.models import FoodAnalysisCall
from ai.provider import (
    FOOD_ANALYSIS_INSTRUCTIONS,
    ProviderFoodAnalysis,
    ProviderOutputError,
    ProviderResult,
)
from ai.services import create_food_analysis

User = get_user_model()


@pytest.mark.django_db
def test_service_retains_photo_and_records_validated_provider_result():
    user = User.objects.create_user(email="service@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={
            "no_food_visible": False,
            "items": [
                {
                    "name": "Chicken",
                    "portion": "2 pieces",
                    "quantity": "1.00",
                    "calories": "360.00",
                    "protein_g": "38.00",
                    "fiber_g": "0.00",
                },
                {
                    "name": "Broccoli",
                    "portion": "1 cup",
                    "quantity": "1.00",
                    "calories": "180.00",
                    "protein_g": "3.00",
                    "fiber_g": "8.00",
                },
            ],
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
            "no_food_visible": False,
            "items": [
                {
                    "name": "Yogurt",
                    "portion": "1 cup",
                    "quantity": "1.00",
                    "calories": "123.456",
                    "protein_g": "10.005",
                    "fiber_g": "0.333",
                }
            ],
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
def test_no_food_result_records_a_billable_failure_and_raises_domain_error():
    user = User.objects.create_user(email="no-food@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={"no_food_visible": True, "items": []},
        provider_request_id="resp_no_food",
        model="gpt-5-mini-2026-08-01",
        input_tokens=800,
        output_tokens=20,
        usage={"input_tokens": 800, "output_tokens": 20},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/desk.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
        pytest.raises(FoodAnalysisNoFoodVisible),
    ):
        create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/desk.jpg",
            description="",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.failure_category == "no_food_visible"
    assert call.response_payload == provider.payload
    assert call.provider_request_id == "resp_no_food"
    assert call.input_tokens == 800
    assert call.output_tokens == 20
    assert call.quota_debited_at is not None
    assert call.estimated_cost_usd is not None


@pytest.mark.django_db
def test_contradictory_no_food_result_is_invalid_and_keeps_provider_diagnostics():
    user = User.objects.create_user(email="contradiction@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={
            "no_food_visible": True,
            "items": [
                {
                    "name": "Coffee",
                    "portion": "1 cup",
                    "quantity": "1.00",
                    "calories": 2,
                    "protein_g": 0,
                    "fiber_g": 0,
                }
            ],
        },
        provider_request_id="resp_contradiction",
        model="gpt-5-mini-2026-08-01",
        input_tokens=750,
        output_tokens=30,
        usage={"input_tokens": 750, "output_tokens": 30},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/drink.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
        pytest.raises(ValidationError, match="contradicted no_food_visible"),
    ):
        create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/drink.jpg",
            description="coffee",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.failure_category == "invalid_model_output"
    assert call.failure_message == "Provider result contradicted no_food_visible."
    assert call.response_payload == provider.payload
    assert call.provider_request_id == "resp_contradiction"
    assert call.input_tokens == 750
    assert call.output_tokens == 30
    assert call.usage == provider.usage
    assert call.estimated_cost_usd is not None
    assert call.quota_debited_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"no_food_visible": "yes", "items": []},
        {"no_food_visible": True, "items": None},
    ],
    ids=("non-boolean-flag", "non-list-items"),
)
def test_malformed_provider_payload_raises_the_public_invalid_output_error(payload):
    user = User.objects.create_user(email="malformed@example.com", timezone="UTC")
    provider = ProviderResult(
        payload=payload,
        provider_request_id="resp_malformed",
        model="gpt-5-mini-2026-08-01",
        input_tokens=600,
        output_tokens=10,
        usage={"input_tokens": 600, "output_tokens": 10},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/meal.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
        pytest.raises(ValidationError, match="invalid structured output"),
    ):
        create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/meal.jpg",
            description="",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.failure_category == "invalid_model_output"
    assert call.failure_message == "Provider returned invalid structured output."
    assert call.response_payload == provider.payload


@pytest.mark.django_db
def test_visible_zero_calorie_drink_remains_a_valid_analysis():
    user = User.objects.create_user(email="zero-drink@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={
            "no_food_visible": False,
            "items": [
                {
                    "name": "Diet soda",
                    "portion": "1 can",
                    "quantity": "1.00",
                    "calories": 0,
                    "protein_g": 0,
                    "fiber_g": 0,
                }
            ],
        },
        provider_request_id="resp_zero_drink",
        model="gpt-5-mini-2026-08-01",
        input_tokens=700,
        output_tokens=40,
        usage={"input_tokens": 700, "output_tokens": 40},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/drink.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
    ):
        result = create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/drink.jpg",
            description="diet soda",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.SUCCEEDED
    assert result["calories"] == "0.00"
    assert result["items"][0]["name"] == "Diet soda"


@pytest.mark.django_db
def test_empty_items_with_food_visible_false_remain_invalid_output():
    user = User.objects.create_user(email="empty-visible@example.com", timezone="UTC")
    provider = ProviderResult(
        payload={"no_food_visible": False, "items": []},
        provider_request_id="resp_empty",
        model="gpt-5-mini-2026-08-01",
        input_tokens=700,
        output_tokens=10,
        usage={"input_tokens": 700, "output_tokens": 10},
    )
    with (
        mock.patch(
            "uploads.services.retain_analysis_object",
            return_value=f"analyses/{user.pk}/meal.jpg",
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
        pytest.raises(ValidationError),
    ):
        create_food_analysis(
            user=user,
            photo_key=f"pending/{user.pk}/meal.jpg",
            description="",
        )

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.failure_category == "invalid_model_output"
    assert call.response_payload == provider.payload
    assert call.quota_debited_at is not None


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
        pytest.raises(ValidationError, match="invalid structured output"),
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


def test_provider_schema_allows_an_honest_empty_no_food_result():
    schema = ProviderFoodAnalysis.model_json_schema()
    items = schema["properties"]["items"]

    assert set(schema["required"]) == {"no_food_visible", "items"}
    assert "minItems" not in items
    assert items["maxItems"] == 30
    assert ProviderFoodAnalysis(no_food_visible=True, items=[]).items == []


def test_provider_instructions_keep_no_food_and_zero_calorie_rules():
    """Guard prompt rules; only a live provider call can prove model behavior."""
    assert "true only when the image shows no food or drink" in FOOD_ANALYSIS_INSTRUCTIONS
    assert "including zero-calorie drinks" in FOOD_ANALYSIS_INSTRUCTIONS


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


def _quantity_provider(items):
    """One payload builder, so a future provider field lands in one place."""
    return ProviderResult(
        payload={"no_food_visible": False, "items": items},
        provider_request_id="resp_quantity",
        model="gpt-5-mini-2026-08-01",
        input_tokens=900,
        output_tokens=150,
        usage={"input_tokens": 900, "output_tokens": 150},
    )


def _run_analysis(user, provider):
    with (
        mock.patch(
            "uploads.services.retain_analysis_object", return_value=f"analyses/{user.pk}/m.jpg"
        ),
        mock.patch("uploads.services.presign_download", return_value="https://signed.invalid"),
        mock.patch("ai.services.analyze_food", return_value=provider),
    ):
        return create_food_analysis(user=user, photo_key=f"pending/{user.pk}/m.jpg", description="")


@pytest.mark.django_db
def test_four_eggs_return_one_item_with_a_count_and_per_unit_macros():
    """The shape MAC-76 exists to produce.

    Before it, the schema had no quantity, so the model wrote the count into
    the name: one item called "4 boiled eggs" carrying four eggs' macros, with
    the mobile mapper forcing quantity to 1. That row reads correctly and
    cannot be edited correctly, because nothing in it says a unit is one egg.
    """
    user = User.objects.create_user(email="eggs@example.com", timezone="UTC")
    provider = _quantity_provider(
        [
            {
                "name": "boiled egg",
                "portion": "1 egg",
                "quantity": "4.00",
                "calories": "78.00",
                "protein_g": "6.30",
                "fiber_g": "0.00",
            }
        ]
    )

    result = _run_analysis(user, provider)

    item = result["items"][0]
    assert item["name"] == "boiled egg"
    assert item["portion"] == "1 egg"
    assert item["quantity"] == "4.00"
    # The item describes one egg.
    assert item["calories"] == "78.00"
    assert item["protein_g"] == "6.30"
    # The totals describe four.
    assert result["calories"] == "312.00"
    assert result["protein_g"] == "25.20"
    assert result["fiber_g"] == "0.00"


@pytest.mark.django_db
def test_a_single_item_still_totals_to_its_own_macros():
    """Quantity 1 has to leave the pre-MAC-76 behaviour exactly where it was."""
    user = User.objects.create_user(email="single@example.com", timezone="UTC")
    provider = _quantity_provider(
        [
            {
                "name": "banana",
                "portion": "1 medium banana",
                "quantity": "1.00",
                "calories": "105.00",
                "protein_g": "1.30",
                "fiber_g": "3.10",
            }
        ]
    )

    result = _run_analysis(user, provider)

    assert result["items"][0]["quantity"] == "1.00"
    assert result["calories"] == "105.00"
    assert result["fiber_g"] == "3.10"


@pytest.mark.django_db
def test_totals_round_the_sum_once_rather_than_each_product():
    """Pin the rounding order, because both orders look right in review.

    Three items, each 1.5 units at 1.01 kcal. One product is exactly 1.5150, so
    the third decimal is where the two orders split. Summing the exact products
    gives 4.5450, which rounds once to 4.55. Rounding each product first gives
    1.52, three times, which sums to 4.56.

    `itemTotals` in apps/mobile/lib/entry-items.ts sums exact products in
    integer hundredths and rounds once, so it answers 4.55 too. The Review
    screen and the saved entry agree only while both sides pick the same order.
    A penny is a small bug and an unexplainable one.
    """
    user = User.objects.create_user(email="rounding@example.com", timezone="UTC")
    item = {
        "name": "sauce",
        "portion": "1 tsp",
        "quantity": "1.50",
        "calories": "1.01",
        "protein_g": "0.00",
        "fiber_g": "0.00",
    }
    provider = _quantity_provider([dict(item), dict(item), dict(item)])

    result = _run_analysis(user, provider)

    assert result["calories"] == "4.55", "rounding each product first would give 4.56"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "quantity",
    ["0.00", "-1.00", "1000000.00"],
    ids=("zero", "negative", "above-the-column-limit"),
)
def test_an_unusable_quantity_fails_as_invalid_model_output(quantity):
    """The provider schema cannot carry this floor, so the serializer does.

    `ProviderFoodItem.quantity` uses `ge=0` rather than `gt=0` on purpose. See
    the comment above that class: a keyword the decoder grammar rejects breaks
    every call, while a bad value reaching here breaks one.
    """
    user = User.objects.create_user(email="badquantity@example.com", timezone="UTC")
    provider = _quantity_provider(
        [
            {
                "name": "toast",
                "portion": "1 slice",
                "quantity": quantity,
                "calories": "80.00",
                "protein_g": "3.00",
                "fiber_g": "1.00",
            }
        ]
    )

    with pytest.raises(ValidationError):
        _run_analysis(user, provider)

    call = FoodAnalysisCall.objects.get()
    assert call.status == FoodAnalysisCall.Status.FAILED
    assert call.failure_category == "invalid_model_output"


def test_provider_schema_carries_quantity_as_a_plain_number():
    """Quantity is a float here for the same reason the macros are floats."""
    item = ProviderFoodAnalysis.model_json_schema()["$defs"]["ProviderFoodItem"]

    assert item["properties"]["quantity"]["type"] == "number"
    assert "anyOf" not in item["properties"]["quantity"]
    assert "quantity" in item["required"]


def test_provider_instructions_ask_for_a_count_rather_than_a_number_in_the_name():
    """Guard prompt rules; only a live provider call can prove model behavior."""
    assert "Group identical repeated food into one item" in FOOD_ANALYSIS_INSTRUCTIONS
    assert "'boiled egg', not '4 boiled eggs'" in FOOD_ANALYSIS_INSTRUCTIONS
    assert "'1 egg', not '4 eggs'" in FOOD_ANALYSIS_INSTRUCTIONS
    assert "for a single unit" in FOOD_ANALYSIS_INSTRUCTIONS
