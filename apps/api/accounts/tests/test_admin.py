"""Tests for the User admin.

Only the parts Apple-only sign-in changed. Under Apple-only most users have no
email, so anything in the admin keyed on email alone silently stops working for
the majority of the table -- a failure that renders as "0 results" rather than
an error, which is exactly the kind that survives a manual click-through.

These assert on `cl.result_count`, the ChangeList in the response context,
rather than on the page HTML. The changelist echoes the search term back into
the search box, so `term in response.content` is true even when the search
matched nothing.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

APPLE_SUB = "000123.abc4567def.8901"


@pytest.fixture
def staff_client(client, db):
    admin = User.objects.create_superuser(email="staff@example.com", password="pw-not-real-12345")
    client.force_login(admin)
    return client


def search_users(client, term):
    response = client.get(reverse("admin:accounts_user_changelist"), {"q": term})
    assert response.status_code == 200
    return response.context["cl"]


@pytest.mark.django_db
def test_admin_finds_an_apple_user_by_subject(staff_client):
    """This user has no email, so apple_user_id is the only thing that can
    reach them. Without it in search_fields the account is unreachable."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)

    changelist = search_users(staff_client, APPLE_SUB)

    assert changelist.result_count == 1
    assert changelist.queryset.get() == user


@pytest.mark.django_db
def test_admin_still_finds_a_user_by_email(staff_client):
    """Guards against the search being narrowed to the subject rather than widened."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB, email="finds.me@example.com")

    changelist = search_users(staff_client, "finds.me@example.com")

    assert changelist.result_count == 1
    assert changelist.queryset.get() == user


@pytest.mark.django_db
def test_admin_change_page_renders_for_a_user_with_no_email(staff_client):
    """The change form renders the object through __str__, which returns
    Optional[str] straight from a nullable column. This is the page that would
    break if the fallback were removed."""
    user = User.objects.create_apple_user(apple_user_id=APPLE_SUB)

    response = staff_client.get(reverse("admin:accounts_user_change", args=[user.pk]))

    assert response.status_code == 200
    assert APPLE_SUB in response.content.decode()
