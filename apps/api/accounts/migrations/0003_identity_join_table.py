"""Move Apple's subject claim off User and into its own Identity table.

Hand-ordered. `makemigrations` emitted RemoveField *before* CreateModel, which
drops the data before there is anywhere to put it. The three steps here have to
run in this order, and the middle one is not something the autodetector can
write for you: it has no idea that `apple_user_id` and `Identity.subject` mean
the same thing.

`accounts_user` is empty in production (MAC-24), so the copy is a no-op there.
It is not a no-op against a local development database, and writing it is the
difference between a migration that happens to work and one that is correct.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

APPLE = "apple"


def copy_apple_ids_to_identities(apps, schema_editor):
    """Give every user with an apple_user_id a matching Identity row.

    `apps.get_model` rather than importing the real classes: a migration must
    see the schema as it was at this point in history. Importing `accounts.models`
    would give whatever the model looks like *today*, so this file would start
    failing the moment a later migration changes the model -- and it would fail
    on someone else's machine, months from now, replaying history.
    """
    User = apps.get_model("accounts", "User")
    Identity = apps.get_model("accounts", "Identity")
    db = schema_editor.connection.alias

    Identity.objects.using(db).bulk_create(
        [
            Identity(user=user, provider=APPLE, subject=user.apple_user_id)
            for user in User.objects.using(db).exclude(apple_user_id=None)
        ]
    )


def copy_identities_back_to_apple_ids(apps, schema_editor):
    """Reverse: fold Apple identities back onto the user row.

    Lossy by nature, and worth being explicit about rather than raising
    NotImplemented. A user with two identities cannot round-trip into one
    column, so the reverse takes the Apple one and drops the rest. Today nobody
    has two, which is precisely the window in which this migration is cheap.
    """
    User = apps.get_model("accounts", "User")
    Identity = apps.get_model("accounts", "Identity")
    db = schema_editor.connection.alias

    for identity in Identity.objects.using(db).filter(provider=APPLE).select_related("user"):
        user = identity.user
        user.apple_user_id = identity.subject
        user.save(using=db, update_fields=["apple_user_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_remove_user_is_email_verified_alter_user_email"),
    ]

    operations = [
        # 1. Somewhere to put the data.
        migrations.CreateModel(
            name="Identity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "provider",
                    models.CharField(choices=[("apple", "Sign in with Apple")], max_length=32),
                ),
                ("subject", models.CharField(max_length=255)),
                ("is_private_email", models.BooleanField(blank=True, null=True)),
                (
                    "real_user_status",
                    models.IntegerField(
                        blank=True,
                        choices=[(0, "Unsupported"), (1, "Unknown"), (2, "Likely real")],
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_authenticated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="identities",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "identities",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("provider", "subject"), name="unique_provider_subject"
                    )
                ],
            },
        ),
        # 2. Move the data, before the column holding it disappears.
        migrations.RunPython(
            copy_apple_ids_to_identities,
            copy_identities_back_to_apple_ids,
        ),
        # 3. Now the column is redundant.
        migrations.RemoveField(
            model_name="user",
            name="apple_user_id",
        ),
    ]
