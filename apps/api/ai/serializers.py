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
        """Reject an empty list, and nothing else.

        This used to also reject a result whose macros were all zero, as a guard
        against a hallucinated answer. The guard was wrong. A diet soda and a
        photo of a blank wall both come back as zero, zero, zero, so the numbers
        cannot tell the two apart. Everything with no calories lost: diet soda,
        black coffee, plain tea, water, sugar-free gum.

        A validator can only test what the data answers. "Is this list empty" is
        such a question. "Did the model do a good job" is not. To learn whether
        the model saw food, ask it in a field of its own rather than infer it.

        Nothing guards against a useless answer now, and that is the intent. The
        user reviews every item before saving and can edit or drop each one, so a
        bad result costs a tap. A rejected real result costs the feature.
        """
        if not value:
            raise serializers.ValidationError("Return at least one food item.")
        return value


class FoodAnalysisErrorSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
