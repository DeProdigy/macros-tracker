"""Move goal weight to pounds, and keep the two onboarding answers worth keeping.

The autodetector proposed a `RemoveField` plus an `AddField` for the weight
rename, because it cannot tell a rename from a coincidence of shape. That drops
every stored goal weight. There are no rows today, so it would have been silently
harmless, which is exactly what makes it worth not shipping: the migration would
have read as correct right up until the first user had a goal.

So a `RenameField` and a real conversion instead. The `RunPython` step is a
formality against an empty table and it is the part that would matter, so it is
the part that gets written properly.

The reverse is a genuine inverse rather than a `noop`. A migration that cannot go
back is one you find out about while trying to go back.
"""

from decimal import Decimal

import django.core.validators
from django.db import migrations, models

POUNDS_PER_KG = Decimal("2.20462262")


def kilograms_to_pounds(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.exclude(goal_weight_lb=None).iterator():
        user.goal_weight_lb = (user.goal_weight_lb * POUNDS_PER_KG).quantize(Decimal("0.01"))
        user.save(update_fields=["goal_weight_lb"])


def pounds_to_kilograms(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.exclude(goal_weight_lb=None).iterator():
        user.goal_weight_lb = (user.goal_weight_lb / POUNDS_PER_KG).quantize(Decimal("0.01"))
        user.save(update_fields=["goal_weight_lb"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_user_settings_fields"),
    ]

    operations = [
        # Rename first, so the conversion below has a column to work on and the
        # stored values survive the move.
        migrations.RenameField(
            model_name="user",
            old_name="goal_weight_kg",
            new_name="goal_weight_lb",
        ),
        migrations.RunPython(kilograms_to_pounds, pounds_to_kilograms),
        # Widened to six digits and re-bounded. 20-400 kg becomes 44-880 lb.
        migrations.AlterField(
            model_name="user",
            name="goal_weight_lb",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("44")),
                    django.core.validators.MaxValueValidator(Decimal("880")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="current_weight_lb",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("85")),
                    django.core.validators.MaxValueValidator(Decimal("1000")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="sex",
            field=models.CharField(
                blank=True,
                choices=[("female", "Female"), ("male", "Male")],
                default="",
                max_length=16,
            ),
        ),
    ]
