from rest_framework import serializers

from .constants import FOOD_ANALYSIS_QUOTA_CODE, ROLLING_WINDOW


class FoodAnalysisQuotaErrorSerializer(serializers.Serializer):
    """Stable rolling-quota response for the food analysis endpoint."""

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


class FoodAnalysisRequestSerializer(serializers.Serializer):
    photo_key = serializers.CharField(max_length=512)
    description = serializers.CharField(
        max_length=200, allow_blank=True, required=False, default=""
    )


class FoodAnalysisItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    portion = serializers.CharField(max_length=100)
    calories = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    protein_g = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    fiber_g = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class FoodAnalysisResultSerializer(serializers.Serializer):
    analysis_id = serializers.IntegerField()
    calories = serializers.DecimalField(max_digits=12, decimal_places=2)
    protein_g = serializers.DecimalField(max_digits=12, decimal_places=2)
    fiber_g = serializers.DecimalField(max_digits=12, decimal_places=2)
    items = FoodAnalysisItemSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Return at least one food item.")
        if not any(
            item[field] > 0 for item in value for field in ("calories", "protein_g", "fiber_g")
        ):
            raise serializers.ValidationError("Return at least one positive macro value.")
        return value


class FoodAnalysisErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
