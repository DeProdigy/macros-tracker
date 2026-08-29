"""Tests for the TargetVersion admin.

The permission rule is the whole point of this file. `readonly_fields` would
also make the form read-only today, and it is an allowlist maintained by hand:
add a column in a later ticket, forget `admin.py`, and that column is quietly
editable. These tests assert the permission methods rather than the field
tuple, so they keep holding as the model grows.

Asserting through real requests rather than by calling the methods directly.
A permission method returning False is only useful if Django is asking it, and
`has_add_permission` with the wrong signature would still return False while the
button stayed on the page.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from targets.models import TargetVersion

User = get_user_model()

PASSWORD = "pw-not-real-12345"


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="alex@example.com")


@pytest.fixture
def version(owner):
    return TargetVersion.objects.create(
        user=owner,
        calories=2150,
        protein_g=176,
        fiber_g=32,
        source=TargetVersion.Source.MANUAL,
        effective_from=timezone.now().date(),
    )


@pytest.fixture
def superuser_client(client, db):
    admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
    client.force_login(admin)
    return client


@pytest.fixture
def staff_client(client, db):
    """Staff, not superuser. Can reach /admin/ and read this model, nothing more."""
    staff = User.objects.create_user(email="support@example.com", password=PASSWORD)
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    staff.user_permissions.add(
        Permission.objects.get(content_type__app_label="targets", codename="view_targetversion")
    )
    client.force_login(staff)
    return client


def changelist(client):
    return client.get(reverse("admin:targets_targetversion_changelist"))


def change_page(client, version):
    return client.get(reverse("admin:targets_targetversion_change", args=[version.pk]))


# --- superusers ---------------------------------------------------------------


@pytest.mark.django_db
def test_a_superuser_can_open_the_add_form(superuser_client):
    """The owner's call on this PR: the escape hatch for a case the API cannot
    express. A hand-added row skips MAC-39's clamp and MAC-47's
    `onboarding_completed` write, which is why it is superuser-only."""
    response = superuser_client.get(reverse("admin:targets_targetversion_add"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_a_superuser_can_edit_an_existing_version(superuser_client, version):
    response = change_page(superuser_client, version)

    assert response.status_code == 200
    # A rendered form, not the read-only view Django serves without change perms.
    assert response.context["has_change_permission"] is True


@pytest.mark.django_db
def test_created_at_stays_read_only_even_for_a_superuser(superuser_client, version):
    """`auto_now_add` means Django discards anything the form sends. Listed in
    `readonly_fields` so the form says so, rather than offering a field that
    silently does nothing."""
    response = change_page(superuser_client, version)

    admin_form = response.context["adminform"]
    assert "created_at" in admin_form.readonly_fields


# --- staff --------------------------------------------------------------------


@pytest.mark.django_db
def test_staff_can_read_but_not_change(staff_client, version):
    response = change_page(staff_client, version)

    assert response.status_code == 200
    assert response.context["has_change_permission"] is False
    assert response.context["has_add_permission"] is False
    assert response.context["has_delete_permission"] is False


@pytest.mark.django_db
def test_staff_cannot_reach_the_add_form(staff_client):
    response = staff_client.get(reverse("admin:targets_targetversion_add"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_can_still_see_the_list(staff_client, version):
    """Read access is the point of listing this model in the admin at all.
    Support answering "what are this user's targets?" should not need a
    superuser."""
    response = changelist(staff_client)

    assert response.status_code == 200
    assert response.context["cl"].result_count == 1


@pytest.mark.django_db
def test_a_superuser_can_actually_save_a_new_version(superuser_client, owner):
    """POSTs the add form rather than just opening it.

    A GET returning 200 proves nothing about whether the form can save. A
    required field left out of the form -- which is what `readonly_fields` does
    -- renders fine and fails on submit.
    """
    response = superuser_client.post(
        reverse("admin:targets_targetversion_add"),
        {
            "user": owner.pk,
            "calories": 2150,
            "protein_g": 176,
            "fiber_g": 32,
            "source": TargetVersion.Source.MANUAL,
            "ai_rationale": "",
            "effective_from": timezone.now().date().isoformat(),
        },
    )

    assert response.status_code == 302, (
        getattr(response, "context", None) and response.context["adminform"].form.errors
    )
    assert TargetVersion.objects.filter(user=owner).count() == 1


@pytest.mark.django_db
def test_user_is_frozen_once_the_version_exists(superuser_client, version):
    """Reassigning ownership is not what the escape hatch is for.

    Moving a row to another account drags every `DailyLog` pointing at it along,
    which is exactly the history rewrite the append-only model prevents. Editing
    the numbers is a supported repair; changing the owner is not.
    """
    response = change_page(superuser_client, version)

    assert "user" in response.context["adminform"].readonly_fields


@pytest.mark.django_db
def test_user_is_still_settable_on_the_add_form(superuser_client):
    """The other half of the same rule. A flat readonly tuple would freeze
    `user` here too, and Django drops read-only fields from the form, so the add
    would post nothing for it and fail on the not-null constraint."""
    response = superuser_client.get(reverse("admin:targets_targetversion_add"))

    assert "user" not in response.context["adminform"].readonly_fields
