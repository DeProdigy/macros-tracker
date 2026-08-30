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

# The band the new validators enforce, repeated here because a migration must
# not import from models: the model moves on and the migration has to keep
# describing the schema as it was at this point.
NEW_FLOOR_LB = Decimal("85")
NEW_CEILING_LB = Decimal("500")


def refuse_unconvertible_rows(apps, schema_editor):
    """Stop before writing a row the new bounds will reject.

    The old column allowed 20 to 400 kg. The new one allows 85 to 500 lb, which
    is 38.56 to 226.80 kg, so the two do not nest: a legacy value at either
    extreme converts to something the `AlterField` below refuses. Left alone the
    migration would write it anyway, because validators do not run on a
    `RunPython` save, and the row would exist and be unsavable.

    Raising rather than clamping. Clamping would silently change a number a
    person entered, and this migration was hand-written specifically to avoid
    doing that. Raising makes a deploy stop and an operator look, which is the
    right amount of noise for a row nobody expected to exist.

    Against an empty table this does nothing, which is the case today.
    """
    User = apps.get_model("accounts", "User")
    db = schema_editor.connection.alias

    unconvertible = [
        (user.pk, user.goal_weight_lb)
        for user in User.objects.using(db).exclude(goal_weight_lb=None).iterator()
        if not (NEW_FLOOR_LB <= (user.goal_weight_lb * POUNDS_PER_KG) <= NEW_CEILING_LB)
    ]
    if unconvertible:
        raise RuntimeError(
            "These goal weights convert to pounds outside the new "
            f"{NEW_FLOOR_LB}-{NEW_CEILING_LB} lb band, so the migration would write "
            f"rows their own validators reject: {unconvertible}. Decide what each "
            "should become and set it before migrating."
        )


def kilograms_to_pounds(apps, schema_editor):
    # `using=` on both, matching 0003 in this app. Without it a `migrate
    # --database=other` runs the schema change on that database and the data
    # change on the default one, which is a corruption that only shows up on a
    # multi-database setup nobody has yet.
    User = apps.get_model("accounts", "User")
    db = schema_editor.connection.alias
    for user in User.objects.using(db).exclude(goal_weight_lb=None).iterator():
        user.goal_weight_lb = (user.goal_weight_lb * POUNDS_PER_KG).quantize(Decimal("0.01"))
        user.save(using=db, update_fields=["goal_weight_lb"])


def pounds_to_kilograms(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    db = schema_editor.connection.alias
    for user in User.objects.using(db).exclude(goal_weight_lb=None).iterator():
        user.goal_weight_lb = (user.goal_weight_lb / POUNDS_PER_KG).quantize(Decimal("0.01"))
        user.save(using=db, update_fields=["goal_weight_lb"])


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
        migrations.RunPython(refuse_unconvertible_rows, migrations.RunPython.noop),
        migrations.RunPython(kilograms_to_pounds, pounds_to_kilograms),
        # Re-bounded to the band `targets.services` can compute a calorie range
        # for, and deliberately not a conversion of the old 20-400 kg.
        #
        # The two do not nest. 20 kg is 44.09 lb, below the new floor, and 400 kg
        # is 881.85 lb, well above the new ceiling. So a legacy value at either
        # extreme converts to something this AlterField then rejects, and the row
        # would exist while being unsavable through PATCH or the admin.
        #
        # `refuse_unconvertible_rows` above is what stops that happening quietly.
        # The bounds are not the thing to loosen: 500 lb is where the suggested
        # calorie range stops working, and 85 lb is where it starts. A goal of
        # 20 kg was never a real answer either.
        migrations.AlterField(
            model_name="user",
            name="goal_weight_lb",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("85")),
                    django.core.validators.MaxValueValidator(Decimal("500")),
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
                    django.core.validators.MaxValueValidator(Decimal("500")),
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
