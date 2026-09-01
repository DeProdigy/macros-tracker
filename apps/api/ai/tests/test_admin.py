import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from ai.models import FoodAnalysisCall

User = get_user_model()
PASSWORD = "pw-not-real-12345"


@pytest.fixture
def call(db):
    owner = User.objects.create_user(email="alex@example.com")
    return FoodAnalysisCall.objects.create(user=owner, started_at=timezone.now())


@pytest.fixture
def staff_client(client, db):
    staff = User.objects.create_user(email="support@example.com", password=PASSWORD)
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    staff.user_permissions.add(
        Permission.objects.get(content_type__app_label="ai", codename="view_foodanalysiscall")
    )
    client.force_login(staff)
    return client


@pytest.fixture
def superuser_client(client, db):
    admin = User.objects.create_superuser(email="root@example.com", password=PASSWORD)
    client.force_login(admin)
    return client


@pytest.mark.django_db
def test_staff_can_inspect_a_call_but_not_change_it(staff_client, call):
    response = staff_client.get(reverse("admin:ai_foodanalysiscall_change", args=[call.pk]))

    assert response.status_code == 200
    assert response.context["has_change_permission"] is False
    assert response.context["has_add_permission"] is False
    assert response.context["has_delete_permission"] is False


@pytest.mark.django_db
def test_even_a_superuser_cannot_add_change_or_delete_calls(superuser_client, call):
    change = superuser_client.get(reverse("admin:ai_foodanalysiscall_change", args=[call.pk]))
    add = superuser_client.get(reverse("admin:ai_foodanalysiscall_add"))
    delete = superuser_client.get(reverse("admin:ai_foodanalysiscall_delete", args=[call.pk]))

    assert change.status_code == 200
    assert change.context["has_change_permission"] is False
    assert add.status_code == 403
    assert delete.status_code == 403
