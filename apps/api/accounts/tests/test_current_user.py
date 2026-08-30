"""Tests for GET and PATCH /api/users/me/.

Two things carry the weight here.

The first is that the write shape cannot reach a server-owned field. A client
that can set its own `onboarding_completed` skips onboarding by sending one
extra key, and that hole is invisible in any test that only checks the fields it
meant to write.

The second is PATCH's own contract: an omitted field is untouched, an explicit
null clears. Those two are the same request byte-for-byte apart from one key, so
the pair of tests is what actually pins the semantics down.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_apple_user(
        apple_user_id="000123.abc.4567",
        email="user@example.com",
    )


@pytest.fixture
def api_client() -> APIClient:
    """Not named `client`: that would shadow pytest-django's own fixture."""
    return APIClient()


@pytest.fixture
def authed_client(api_client, user) -> APIClient:
    access = RefreshToken.for_user(user).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return api_client


# --- GET --------------------------------------------------------------------


@pytest.mark.django_db
def test_get_returns_the_authenticated_user(authed_client, user):
    response = authed_client.get(reverse("users:current"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["id"] == user.pk
    assert response.data["email"] == "user@example.com"
    assert response.data["onboarding_completed"] is False


@pytest.mark.django_db
def test_get_never_exposes_password_or_permission_fields(authed_client):
    """The reason the serializer lists its fields instead of using `__all__`.

    `__all__` on this model publishes the password hash, `is_superuser`, and
    every permission relation into the generated mobile client.
    """
    response = authed_client.get(reverse("users:current"))

    assert set(response.data) == {
        "id",
        "email",
        "name",
        "timezone",
        "onboarding_completed",
        "sex",
        "current_weight_lb",
        "goal_weight_lb",
        "goal_timeline_weeks",
        "training_days_per_week",
        "dietary_constraints",
    }


@pytest.mark.django_db
def test_get_401s_without_a_token(api_client):
    response = api_client.get(reverse("users:current"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_get_401s_with_an_expired_token(api_client, user):
    """Proves the access lifetime is enforced on the read path.

    The token is minted valid and then backdated past its own expiry, rather
    than waiting 15 minutes or patching the setting.
    """
    access = AccessToken.for_user(user)
    access.set_exp(from_time=access.current_time - timedelta(hours=1))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = api_client.get(reverse("users:current"))

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- PATCH ------------------------------------------------------------------


@pytest.mark.django_db
def test_patch_writes_sex_and_current_weight(authed_client, user):
    """The two answers MAC-53 started storing, on the success path.

    Kept apart from the four older settings fields because they arrive from
    somewhere else: onboarding answers the app asks for, rather than settings a
    user opens a screen to fill in.
    """
    response = authed_client.patch(
        reverse("users:current"),
        {"sex": "female", "current_weight_lb": "155.00"},
    )

    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.sex == "female"
    assert user.current_weight_lb == Decimal("155.00")


@pytest.mark.django_db
def test_sex_clears_with_an_empty_string_and_not_with_null(authed_client, user):
    """The one inconsistency on this serializer, pinned so it stays deliberate.

    Every other clearable field here takes `null`. `sex` is a blank-string column
    and takes `""`. Review asked for `allow_null` with a coercion to match the
    rest, and it does not survive the toolchain: `allow_null` on a blank-capable
    ChoiceField makes drf-spectacular emit `nullable: true` *and* a `NullEnum`
    member, and orval refuses the result with a duplicate-name error. The
    generated client stops building, which is worse than the papercut.

    So the difference is documented in the field's help text, which reaches the
    OpenAPI schema and the client. This test is what stops someone "fixing" the
    asymmetry without discovering that cost again.
    """
    user.sex = "male"
    user.save(update_fields=["sex"])

    assert (
        authed_client.patch(reverse("users:current"), {"sex": ""}).status_code == status.HTTP_200_OK
    )
    user.refresh_from_db()
    assert user.sex == ""

    assert (
        authed_client.patch(reverse("users:current"), {"sex": None}).status_code
        == status.HTTP_400_BAD_REQUEST
    )


@pytest.mark.django_db
def test_the_read_shape_reports_an_unanswered_sex_as_an_empty_string(authed_client):
    """What the generated client has to be able to express.

    Before this, `User.sex` was typed `SexEnum` with no blank member, so a client
    switching over it with no default would have every unanswered user fall
    through the switch with nothing raised.
    """
    response = authed_client.get(reverse("users:current"))

    assert response.data["sex"] == ""


@pytest.mark.django_db
def test_patch_writes_the_settings_fields(authed_client, user):
    response = authed_client.patch(
        reverse("users:current"),
        {
            "goal_weight_lb": "173.00",
            "goal_timeline_weeks": 12,
            "training_days_per_week": 4,
            "dietary_constraints": "no dairy",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.goal_weight_lb == Decimal("173.00")
    assert user.goal_timeline_weeks == 12
    assert user.training_days_per_week == 4
    assert user.dietary_constraints == "no dairy"


@pytest.mark.django_db
def test_patch_returns_the_full_user(authed_client):
    """The response is the read shape, so one round trip refreshes the cache."""
    response = authed_client.patch(reverse("users:current"), {"training_days_per_week": 3})

    assert response.data["training_days_per_week"] == 3
    assert "onboarding_completed" in response.data


@pytest.mark.django_db
def test_patch_leaves_omitted_fields_alone(authed_client, user):
    user.goal_weight_lb = Decimal("176.00")
    user.save()

    authed_client.patch(reverse("users:current"), {"training_days_per_week": 5})

    user.refresh_from_db()
    assert user.goal_weight_lb == Decimal("176.00")


@pytest.mark.django_db
def test_patch_clears_a_field_with_an_explicit_null(authed_client, user):
    """The other half of the previous test, and the reason this is not PUT."""
    user.goal_weight_lb = Decimal("176.00")
    user.save()

    authed_client.patch(reverse("users:current"), {"goal_weight_lb": None})

    user.refresh_from_db()
    assert user.goal_weight_lb is None


@pytest.mark.django_db
def test_patch_stores_a_null_constraint_as_empty_text(authed_client, user):
    """The column is not nullable, so "clear it" lands as "".

    One empty value in the database, and clients still say it the same way they
    clear the numeric fields.
    """
    user.dietary_constraints = "vegan"
    user.save()

    authed_client.patch(reverse("users:current"), {"dietary_constraints": None})

    user.refresh_from_db()
    assert user.dietary_constraints == ""


@pytest.mark.django_db
def test_patch_updates_the_timezone(authed_client, user):
    """Sent on app launch (doc 02), so days bucket to where the user actually is."""
    authed_client.patch(reverse("users:current"), {"timezone": "Europe/London"})

    user.refresh_from_db()
    assert user.timezone == "Europe/London"


@pytest.mark.django_db
def test_patch_cannot_set_onboarding_completed(authed_client, user):
    """The hole a shared read/write serializer would open.

    Unknown keys are ignored rather than rejected, so this is silent when it
    goes wrong -- which is exactly why it is asserted.
    """
    authed_client.patch(reverse("users:current"), {"onboarding_completed": True})

    user.refresh_from_db()
    assert user.onboarding_completed is False


@pytest.mark.django_db
def test_patch_cannot_rewrite_the_email(authed_client, user):
    """Email comes from Apple's verified claims, never from a client field."""
    authed_client.patch(reverse("users:current"), {"email": "attacker@example.com"})

    user.refresh_from_db()
    assert user.email == "user@example.com"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"goal_weight_lb": "5.00"},
        # The 500 this PR exists to prevent. 50 lb is below the band
        # `suggested_calorie_range` can describe, and 600 is above it: both make
        # the range invert and raise. The claim that the column validator turns
        # that into a 400 is the reason it sits on the field, so it gets a test
        # rather than trust in DRF copying model validators onto the serializer.
        {"current_weight_lb": "50.00"},
        {"current_weight_lb": "600.00"},
        # Proves the choices actually gate the column, which `test_units.py`
        # assumes when it maps every stored Sex to a calorie floor.
        {"sex": "other"},
        {"goal_weight_lb": "2000.00"},
        {"goal_timeline_weeks": 0},
        {"goal_timeline_weeks": 500},
        {"training_days_per_week": 8},
        {"dietary_constraints": "x" * 501},
    ],
)
def test_patch_rejects_out_of_range_values(authed_client, payload):
    """Bounds live on the model, so the admin and the API reject the same values.

    Not cosmetic: these numbers feed target generation, and a 5 kg goal weight
    produces a calorie floor no clamp downstream should ever have to argue with.
    """
    response = authed_client.patch(reverse("users:current"), payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_patch_401s_without_a_token(api_client):
    response = api_client.patch(reverse("users:current"), {"training_days_per_week": 3})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_put_is_not_routed(authed_client):
    """PUT is deliberately absent: a full replace cannot tell an omitted field
    from a cleared one."""
    response = authed_client.put(reverse("users:current"), {"training_days_per_week": 3})

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
