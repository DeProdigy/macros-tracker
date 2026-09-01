from decimal import Decimal

from rest_framework import serializers

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

    def create(self, validated_data):
        item = services.ManualItem(**validated_data.pop("item"))
        validated_data.pop("timezone")
        return services.create_manual_entry(
            user=self.context["request"].user, item=item, **validated_data
        )


class FoodItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodItem
        fields = ("id", "name", "portion_label", "quantity", "calories", "protein_g", "fiber_g")


class FoodEntrySerializer(serializers.ModelSerializer):
    items = FoodItemSerializer(many=True)

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


def day_data(day: DailyLog | None, local_date):
    if day is None:
        return {
            "local_date": local_date,
            "targets": None,
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
