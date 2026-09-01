from rest_framework import serializers

from .constants import FOOD_ANALYSIS_QUOTA_CODE, ROLLING_WINDOW


class FoodAnalysisQuotaErrorSerializer(serializers.Serializer):
    """Stable response shape for MAC-54's future analysis endpoint."""

    code = serializers.SerializerMethodField()
    detail = serializers.CharField()
    limit = serializers.IntegerField(min_value=1)
    used = serializers.IntegerField(min_value=0)
    window_days = serializers.SerializerMethodField()
    retry_at = serializers.DateTimeField()

    def get_code(self, obj) -> str:
        return FOOD_ANALYSIS_QUOTA_CODE

    def get_window_days(self, obj) -> int:
        return ROLLING_WINDOW.days
