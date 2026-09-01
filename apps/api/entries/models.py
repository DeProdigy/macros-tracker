from django.conf import settings
from django.db import models


class DailyLog(models.Model):
    """One user's entries and captured targets for one local calendar date.

    The first entry creates the row and captures the target version. A read
    must not create it because that would move the capture point from the first
    write to an arbitrary read. The unique constraint makes `get_or_create`
    safe when two entry requests race for the same user and date.
    """

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
    """A logged event with totals copied from its item rows.

    This is deliberate denormalization. Today reads these totals on every
    render, so it must not multiply and sum each item again. The service owns
    both writes inside one transaction. This choice is wrong if item values can
    change without the service updating the entry totals.
    """

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        PHOTO = "photo", "Photo"
        RECENT = "recent", "Recent"

    daily_log = models.ForeignKey(DailyLog, on_delete=models.CASCADE, related_name="entries")
    source = models.CharField(max_length=16, choices=Source.choices)
    description = models.CharField(max_length=200)
    eaten_at = models.DateTimeField()
    calories = models.DecimalField(max_digits=10, decimal_places=2)
    protein_g = models.DecimalField(max_digits=10, decimal_places=2)
    fiber_g = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-eaten_at", "-id")

    def __str__(self) -> str:
        return self.description


class FoodItem(models.Model):
    """One food and its per-unit macros inside an entry.

    Per-unit values preserve what the user entered. `FoodEntry` stores the
    quantity-adjusted totals for fast day reads.
    """

    entry = models.ForeignKey(FoodEntry, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    portion_label = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(max_digits=8, decimal_places=2)
    calories = models.DecimalField(max_digits=10, decimal_places=2)
    protein_g = models.DecimalField(max_digits=10, decimal_places=2)
    fiber_g = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self) -> str:
        return self.name
