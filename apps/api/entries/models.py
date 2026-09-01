from django.conf import settings
from django.db import models


class DailyLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_logs"
    )
    local_date = models.DateField()
    target_version = models.ForeignKey(
        "targets.TargetVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="daily_logs",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "local_date"), name="one_daily_log_per_user_date"
            )
        ]
        ordering = ("-local_date",)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.local_date}"


class FoodEntry(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        PHOTO = "photo", "Photo"
        RECENT = "recent", "Recent"

    daily_log = models.ForeignKey(DailyLog, on_delete=models.CASCADE, related_name="entries")
    source = models.CharField(max_length=16, choices=Source.choices)
    description = models.CharField(max_length=200)
    eaten_at = models.DateTimeField()
    photo_key = models.CharField(max_length=500, blank=True)
    calories = models.DecimalField(max_digits=10, decimal_places=2)
    protein_g = models.DecimalField(max_digits=10, decimal_places=2)
    fiber_g = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-eaten_at", "-id")

    def __str__(self) -> str:
        return self.description


class FoodItem(models.Model):
    entry = models.ForeignKey(FoodEntry, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    portion_label = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    calories = models.DecimalField(max_digits=10, decimal_places=2)
    protein_g = models.DecimalField(max_digits=10, decimal_places=2)
    fiber_g = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self) -> str:
        return self.name
