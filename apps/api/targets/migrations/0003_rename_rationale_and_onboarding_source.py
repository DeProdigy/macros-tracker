"""Drop `ai` from two names that no longer describe anything.

`ai_rationale` becomes `rationale` and the `onboarding_ai` source value becomes
`onboarding`. The AI call was cancelled on 31 Aug 2026 and a template writes the
text now, so both names pointed at a producer that will not exist.

`makemigrations` proposed a `RemoveField` plus an `AddField` for the column,
because it cannot tell a rename from a coincidence of shape. That drops every
stored rationale. There are no rows today, so it would have been silently
harmless, which is exactly what makes it worth not shipping: the migration would
have read as correct right up until the first user had targets. Same reasoning as
`accounts/0006`, and the same fix.

The source value gets a `RunPython` for the same reason. `AlterField` changes the
choices the model validates against and leaves any stored `onboarding_ai` string
sitting in the column, where nothing would ever match it.

Both reverses are real inverses rather than `noop`. A migration that cannot go
back is one you find out about while trying to go back.
"""

from django.db import migrations, models

OLD_SOURCE = "onboarding_ai"
NEW_SOURCE = "onboarding"


def _rewrite_source(apps, schema_editor, old, new):
    TargetVersion = apps.get_model("targets", "TargetVersion")
    # `using=` matching accounts/0003 and 0006. Without it a
    # `migrate --database=other` runs the schema change on that database and the
    # data change on the default one.
    TargetVersion.objects.using(schema_editor.connection.alias).filter(source=old).update(
        source=new
    )


def onboarding_ai_to_onboarding(apps, schema_editor):
    _rewrite_source(apps, schema_editor, OLD_SOURCE, NEW_SOURCE)


def onboarding_to_onboarding_ai(apps, schema_editor):
    _rewrite_source(apps, schema_editor, NEW_SOURCE, OLD_SOURCE)


class Migration(migrations.Migration):
    dependencies = [
        ("targets", "0002_alter_targetversion_ai_rationale"),
    ]

    operations = [
        migrations.RenameField(
            model_name="targetversion",
            old_name="ai_rationale",
            new_name="rationale",
        ),
        migrations.AlterField(
            model_name="targetversion",
            name="rationale",
            field=models.TextField(
                blank=True,
                help_text=(
                    "Plain-English explanation of the numbers, shown under WHY THESE "
                    "NUMBERS on screen 9f. Around 60 words, naming the deficit, the "
                    "rate, and why protein is set from body weight. Empty for a "
                    "manual edit."
                ),
            ),
        ),
        # Data before schema. The new `choices` do not include `onboarding_ai`,
        # and rewriting the rows first means no row is ever left holding a value
        # its own field rejects.
        migrations.RunPython(onboarding_ai_to_onboarding, onboarding_to_onboarding_ai),
        migrations.AlterField(
            model_name="targetversion",
            name="source",
            field=models.CharField(
                choices=[("onboarding", "Onboarding"), ("manual", "Manual edit")],
                max_length=32,
            ),
        ),
    ]
