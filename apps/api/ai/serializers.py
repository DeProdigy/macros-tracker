from rest_framework import serializers


class FoodAnalysisQuotaErrorSerializer(serializers.Serializer):
    """Stable response shape for MAC-54's future analysis endpoint."""

    code = serializers.SerializerMethodField()
    detail = serializers.CharField()
    limit = serializers.IntegerField(min_value=1)
    used = serializers.IntegerField(min_value=0)
    window_days = serializers.SerializerMethodField()
    retry_at = serializers.DateTimeField()

    def get_code(self, obj) -> str:
        return "food_analysis_quota_exceeded"

    def get_window_days(self, obj) -> int:
        return 30
