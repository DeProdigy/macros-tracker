from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from ai.models import FoodAnalysisCall

from . import services
from .models import DailyLog, FoodEntry, FoodItem


class ManualItemWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))
    calories = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    protein_g = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    fiber_g = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))

    def validate(self, attrs):
        if not any(attrs[field] > 0 for field in ("calories", "protein_g", "fiber_g")):
            raise serializers.ValidationError("Enter at least one macro value greater than zero.")
        return attrs


class ManualEntryCreateSerializer(serializers.Serializer):
    local_date = serializers.DateField()
    timezone = serializers.CharField(max_length=64)
    eaten_at = serializers.DateTimeField()
    item = ManualItemWriteSerializer()

    def validate_timezone(self, value: str) -> str:
        user = self.context["request"].user
        if value != user.timezone:
            raise serializers.ValidationError("Synchronize the device timezone and try again.")
        return value

    def validate(self, attrs):
        try:
            zone = ZoneInfo(attrs["timezone"])
        except (ValueError, ZoneInfoNotFoundError):
            raise serializers.ValidationError(
                {"timezone": "Synchronize the device timezone and try again."}
            ) from None
        if attrs["eaten_at"].astimezone(zone).date() != attrs["local_date"]:
            raise serializers.ValidationError("The eaten time is not on the selected local date.")
        return attrs

    def create(self, validated_data):
        item = services.ManualItem(**validated_data.pop("item"))
        validated_data.pop("timezone")
        return services.create_manual_entry(
            user=self.context["request"].user, item=item, **validated_data
        )


class PhotoEntryCreateSerializer(serializers.Serializer):
    local_date = serializers.DateField()
    timezone = serializers.CharField(max_length=64)
    eaten_at = serializers.DateTimeField()
    analysis_id = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        manual = ManualEntryCreateSerializer(context=self.context)
        manual.validate_timezone(attrs["timezone"])
        try:
            zone = ZoneInfo(attrs["timezone"])
        except (ValueError, ZoneInfoNotFoundError):
            raise serializers.ValidationError(
                {"timezone": "Synchronize the device timezone and try again."}
            ) from None
        if attrs["eaten_at"].astimezone(zone).date() != attrs["local_date"]:
            raise serializers.ValidationError("The eaten time is not on the selected local date.")
        call = FoodAnalysisCall.objects.filter(
            pk=attrs["analysis_id"],
            user=self.context["request"].user,
            status=FoodAnalysisCall.Status.SUCCEEDED,
        ).first()
        if call is None or hasattr(call, "food_entry"):
            raise serializers.ValidationError(
                {"analysis_id": "Choose a completed analysis that has not been saved."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("timezone")
        try:
            return services.create_photo_entry(user=self.context["request"].user, **validated_data)
        except (FoodAnalysisCall.DoesNotExist, ValueError):
            raise serializers.ValidationError(
                {"analysis_id": "Choose a completed analysis that has not been saved."}
            ) from None


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = ("id", "name", "portion_label", "quantity", "calories", "protein_g", "fiber_g")


class FoodEntrySerializer(serializers.ModelSerializer):
    items = FoodItemSerializer(many=True)
    photo_url = serializers.SerializerMethodField()

    def get_photo_url(self, obj) -> str | None:
        if not obj.photo_key:
            return None
        from uploads.services import presign_download

        return presign_download(key=obj.photo_key)

    class Meta:
        model = FoodEntry
        fields = (
            "id",
            "source",
            "description",
            "eaten_at",
            "calories",
            "protein_g",
            "fiber_g",
            "photo_url",
            "items",
        )


class DayTargetSerializer(serializers.Serializer):
    calories = serializers.IntegerField()
    protein_g = serializers.IntegerField()
    fiber_g = serializers.IntegerField()


class DaySerializer(serializers.Serializer):
    local_date = serializers.DateField()
    targets = DayTargetSerializer(allow_null=True)
    calories = serializers.DecimalField(max_digits=12, decimal_places=2)
    protein_g = serializers.DecimalField(max_digits=12, decimal_places=2)
    fiber_g = serializers.DecimalField(max_digits=12, decimal_places=2)
    entries = FoodEntrySerializer(many=True)


def day_data(day: DailyLog | None, local_date, effective_target=None):
    if day is None:
        return {
            "local_date": local_date,
            "targets": (
                {
                    "calories": effective_target.calories,
                    "protein_g": effective_target.protein_g,
                    "fiber_g": effective_target.fiber_g,
                }
                if effective_target
                else None
            ),
            "calories": Decimal("0"),
            "protein_g": Decimal("0"),
            "fiber_g": Decimal("0"),
            "entries": [],
        }
    entries = list(day.entries.prefetch_related("items").all())
    target = day.target_version
    return {
        "local_date": day.local_date,
        "targets": (
            {"calories": target.calories, "protein_g": target.protein_g, "fiber_g": target.fiber_g}
            if target
            else None
        ),
        "calories": sum((entry.calories for entry in entries), Decimal("0")),
        "protein_g": sum((entry.protein_g for entry in entries), Decimal("0")),
        "fiber_g": sum((entry.fiber_g for entry in entries), Decimal("0")),
        "entries": entries,
    }
