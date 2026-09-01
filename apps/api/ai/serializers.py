from rest_framework import serializers


class FoodAnalysisQuotaErrorSerializer(serializers.Serializer):
    """Stable response shape for MAC-54's future analysis endpoint."""

    code = serializers.CharField(default="food_analysis_quota_exceeded")
    detail = serializers.CharField()
    limit = serializers.IntegerField(min_value=1)
    used = serializers.IntegerField(min_value=0)
    window_days = serializers.IntegerField(default=30)
    retry_at = serializers.DateTimeField()
