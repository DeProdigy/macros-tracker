from datetime import UTC, datetime

from ai.serializers import FoodAnalysisQuotaErrorSerializer


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
