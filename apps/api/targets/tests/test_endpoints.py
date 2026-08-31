from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from targets.models import TargetVersion

User = get_user_model()

TODAY = timezone.now().date()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="alex@example.com", sex="male", current_weight_lb=Decimal("155.00")
    )


@pytest.fixture
def weightless(db):
    return User.objects.create_user(email="skipped@example.com")


@pytest.fixture
def client_for():
    def build(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return build


def payload(**overrides):
    return {
        "calories": 2150,
        "protein_g": 140,
        "fiber_g": 30,
        "effective_from": TODAY.isoformat(),
        **overrides,
    }


def make_version(user, **overrides):
    fields = {
        "calories": 2150,
        "protein_g": 140,
        "fiber_g": 30,
        "source": TargetVersion.Source.MANUAL,
        "effective_from": TODAY,
        **overrides,
    }
    return TargetVersion.objects.create(user=user, **fields)


# --- create -------------------------------------------------------------------


@pytest.mark.django_db
def test_creating_targets_returns_201_and_the_stored_row(user, client_for):
    response = client_for(user).post(reverse("targets:list-create"), payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["calories"] == 2150
    assert response.data["source"] == "manual"
    assert TargetVersion.objects.for_user(user).count() == 1


@pytest.mark.django_db
def test_a_second_create_leaves_the_first_row_alone(user, client_for):
    first = make_version(user, calories=2000)

    client_for(user).post(reverse("targets:list-create"), payload(calories=2400), format="json")

    first.refresh_from_db()
    assert first.calories == 2000
    assert TargetVersion.objects.for_user(user).count() == 2


@pytest.mark.django_db
def test_effective_from_is_required(user, client_for):
    body = payload()
    del body["effective_from"]

    response = client_for(user).post(reverse("targets:list-create"), body, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "effective_from" in response.data


@pytest.mark.django_db
def test_a_future_effective_from_is_refused(user, client_for):
    body = payload(effective_from=(TODAY + timedelta(days=3)).isoformat())

    response = client_for(user).post(reverse("targets:list-create"), body, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert TargetVersion.objects.for_user(user).count() == 0


@pytest.mark.django_db
def test_tomorrow_is_accepted_because_a_client_can_be_a_day_ahead_of_utc(user, client_for):
    body = payload(effective_from=(TODAY + timedelta(days=1)).isoformat())

    response = client_for(user).post(reverse("targets:list-create"), body, format="json")

    assert response.status_code == status.HTTP_201_CREATED


# --- the two clamp tiers ------------------------------------------------------


@pytest.mark.django_db
def test_a_value_outside_the_suggested_range_is_stored_as_typed(user, client_for):
    response = client_for(user).post(
        reverse("targets:list-create"), payload(calories=1200), format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["calories"] == 1200


@pytest.mark.django_db
@pytest.mark.parametrize("calories", [999, 5001])
def test_a_value_outside_the_absolute_range_is_refused(user, client_for, calories):
    response = client_for(user).post(
        reverse("targets:list-create"), payload(calories=calories), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert TargetVersion.objects.for_user(user).count() == 0


@pytest.mark.django_db
def test_a_user_with_no_weight_can_still_set_targets(weightless, client_for):
    response = client_for(weightless).post(reverse("targets:list-create"), payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_calories_are_still_bounded_without_a_weight(weightless, client_for):
    response = client_for(weightless).post(
        reverse("targets:list-create"), payload(calories=400), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_protein_is_still_bounded_when_only_the_sex_answer_is_missing(client_for, db):
    """The hole review found in the first version.

    `reject_outside_absolute` takes a weight, not a profile, because none of the
    three bounds reads sex. Gating on both dropped the protein guard for a user
    who answered the weight question and skipped the sex one, with the number it
    needed sitting right there.
    """
    sexless = User.objects.create_user(
        email="nosex@example.com", current_weight_lb=Decimal("155.00")
    )

    response = client_for(sexless).post(
        reverse("targets:list-create"), payload(protein_g=900), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_protein_is_unbounded_without_a_weight(weightless, client_for):
    response = client_for(weightless).post(
        reverse("targets:list-create"), payload(protein_g=900), format="json"
    )

    assert response.status_code == status.HTTP_201_CREATED


# --- list ---------------------------------------------------------------------


@pytest.mark.django_db
def test_the_list_is_newest_first(user, client_for):
    make_version(user, calories=2000)
    make_version(user, calories=2100)
    make_version(user, calories=2200)

    response = client_for(user).get(reverse("targets:list-create"))

    assert [row["calories"] for row in response.data] == [2200, 2100, 2000]


@pytest.mark.django_db
def test_the_list_is_empty_for_a_user_with_no_targets(user, client_for):
    response = client_for(user).get(reverse("targets:list-create"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data == []


@pytest.mark.django_db
def test_one_user_never_sees_another_users_targets(user, weightless, client_for):
    make_version(weightless, calories=3000)

    response = client_for(user).get(reverse("targets:list-create"))

    assert response.data == []


# --- current ------------------------------------------------------------------


@pytest.mark.django_db
def test_current_returns_the_newest_version(user, client_for):
    make_version(user, calories=2000)
    make_version(user, calories=2200)

    response = client_for(user).get(reverse("targets:current"))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["calories"] == 2200


@pytest.mark.django_db
def test_current_is_404_before_any_targets_exist(user, client_for):
    response = client_for(user).get(reverse("targets:current"))

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_current_never_reaches_another_users_row(user, weightless, client_for):
    make_version(weightless, calories=3000)

    assert client_for(user).get(reverse("targets:current")).status_code == (
        status.HTTP_404_NOT_FOUND
    )


# --- auth ---------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("route", ["targets:list-create", "targets:current"])
def test_every_route_needs_authentication_to_read(route):
    assert APIClient().get(reverse(route)).status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_creating_targets_needs_authentication():
    """The write is where a missing permission actually costs something, and the
    read-only version of this test did not cover it."""
    response = APIClient().post(reverse("targets:list-create"), payload(), format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert TargetVersion.objects.count() == 0


# --- MAC-47: the first target completes onboarding ---------------------------
#
# The bug these guard: `onboarding_completed` was read by two mobile routes and
# written by nothing, so a user set targets, closed the app, and reopened it in
# onboarding. Forever.


def test_a_first_target_completes_onboarding(user, client_for):
    assert user.onboarding_completed is False

    response = client_for(user).post(reverse("targets:list-create"), payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    user.refresh_from_db()
    assert user.onboarding_completed is True


def test_the_round_trip_the_gate_actually_makes(user, client_for):
    """Create a target, then refetch the user the way the app does on launch.

    The unit test above reads the database directly. This one goes through
    `GET /api/users/me/`, because that is the response the launch gate reads and
    the serializer is where the field could still be dropped.
    """
    client = client_for(user)
    client.post(reverse("targets:list-create"), payload(), format="json")

    me = client.get(reverse("users:current"))

    assert me.data["onboarding_completed"] is True


def test_a_later_target_leaves_the_flag_alone(user, client_for):
    client = client_for(user)
    client.post(reverse("targets:list-create"), payload(), format="json")
    user.refresh_from_db()
    first_state = user.onboarding_completed

    client.post(reverse("targets:list-create"), payload(calories=2200), format="json")

    user.refresh_from_db()
    assert first_state is True
    assert user.onboarding_completed is True
    assert TargetVersion.objects.for_user(user).count() == 2


def test_a_rejected_target_does_not_complete_onboarding(user, client_for):
    """The flag and the row move together, or neither moves.

    A 400 here is the cheap version. The expensive version is a target that
    saves while the flag write fails, which leaves a user who owns targets and
    is still told to go and set some.
    """
    response = client_for(user).post(
        reverse("targets:list-create"), payload(calories=400), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    user.refresh_from_db()
    assert user.onboarding_completed is False


def test_the_flag_is_restored_if_an_operator_clears_it(user, client_for):
    """The condition is "not completed yet", not "this is the first version".

    Worth pinning, because the two are not the same and the difference is the
    reason for a conditional UPDATE rather than a count. A user whose flag was
    cleared by hand gets it back on their next target, which is the answer that
    keeps the launch gate honest.
    """
    client = client_for(user)
    client.post(reverse("targets:list-create"), payload(), format="json")
    User.objects.filter(pk=user.pk).update(onboarding_completed=False)

    client.post(reverse("targets:list-create"), payload(calories=2200), format="json")

    user.refresh_from_db()
    assert user.onboarding_completed is True
