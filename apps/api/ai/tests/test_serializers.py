from datetime import UTC, datetime

from ai.serializers import FoodAnalysisQuotaErrorSerializer, FoodAnalysisResultSerializer


def test_quota_error_has_a_stable_machine_readable_shape():
    serializer = FoodAnalysisQuotaErrorSerializer(
        {
            "detail": "Photo analysis limit reached.",
            "limit": 500,
            "used": 500,
            "retry_at": datetime(2026, 9, 2, 12, tzinfo=UTC),
        }
    )

    assert serializer.data == {
        "code": "food_analysis_quota_exceeded",
        "detail": "Photo analysis limit reached.",
        "limit": 500,
        "used": 500,
        "window_days": 30,
        "retry_at": "2026-09-02T12:00:00Z",
    }


def test_callers_cannot_override_the_stable_code_or_window():
    serializer = FoodAnalysisQuotaErrorSerializer(
        {
            "code": "different",
            "detail": "Photo analysis limit reached.",
            "limit": 500,
            "used": 500,
            "window_days": 7,
            "retry_at": datetime(2026, 9, 2, 12, tzinfo=UTC),
        }
    )

    assert serializer.data["code"] == "food_analysis_quota_exceeded"
    assert serializer.data["window_days"] == 30


def _result(items):
    return {
        "analysis_id": 1,
        "calories": "0.00",
        "protein_g": "0.00",
        "fiber_g": "0.00",
        "items": items,
    }


def test_a_zero_calorie_item_is_a_valid_result():
    """A Sunkist Zero is 0 calories, 0 protein, and 0 fiber, and it is real food.

    The serializer used to reject any result whose macros were all zero. The rule
    meant to catch a hallucinated empty answer, but it cannot: an all-zero answer
    about a diet soda and an all-zero answer about a blank wall are the same three
    numbers. Diet soda, black coffee, plain tea, and water all lost to that rule.
    """
    serializer = FoodAnalysisResultSerializer(
        data=_result(
            [
                {
                    "name": "Sunkist Zero Sugar orange soda",
                    "portion": "1 can (12 fl oz)",
                    "quantity": "1.00",
                    "calories": "0.00",
                    "protein_g": "0.00",
                    "fiber_g": "0.00",
                }
            ]
        )
    )

    assert serializer.is_valid(), serializer.errors


def test_an_empty_item_list_is_still_rejected():
    """The non-empty rule survives, because a list can answer that question."""
    serializer = FoodAnalysisResultSerializer(data=_result([]))

    assert not serializer.is_valid()
    assert "items" in serializer.errors
