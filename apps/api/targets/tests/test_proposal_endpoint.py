"""Tests for `POST /api/targets/proposals/`.

The arithmetic lives in `test_proposal.py`. This file covers what the endpoint
adds: authentication, the validation that stops a bad input reaching a formula
that would raise, and the response shape the client is typed against.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from targets.models import TargetVersion
from targets.services import MAXIMUM_SUPPORTED_WEIGHT_LB, MINIMUM_SUPPORTED_WEIGHT_LB

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(email="alex@example.com")


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


def payload(**overrides):
    return {
        "age": 35,
        "sex": "male",
        "height_in": 71,
        "weight_lb": "155.00",
        "goal": "cut",
        "activity": "moderate",
        **overrides,
    }


def test_the_six_answers_come_back_as_three_numbers(client):
    response = client.post(reverse("targets:proposals"), payload(), format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["targets"] == {"calories": 2059, "protein_g": 155, "fiber_g": 29}


def test_the_response_carries_everything_screen_9f_draws(client):
    response = client.post(reverse("targets:proposals"), payload(), format="json")

    assert set(response.data) == {"targets", "baseline", "clamped", "rationale"}
    assert response.data["clamped"] is False
    assert response.data["baseline"] == response.data["targets"]
    assert "2,059 calories" in response.data["rationale"]


def test_nothing_is_stored(client, user):
    """200, not 201, and the reason is visible in the database.

    A proposal is computed and returned. The user accepts it by posting to
    `/api/targets/`, which is the only thing that creates a version.
    """
    client.post(reverse("targets:proposals"), payload(), format="json")

    assert TargetVersion.objects.filter(user=user).count() == 0
    user.refresh_from_db()
    # And it does not complete onboarding, because they have no targets yet.
    assert user.onboarding_completed is False


def test_a_proposal_needs_authentication():
    response = APIClient().post(reverse("targets:proposals"), payload(), format="json")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_the_same_answers_always_give_the_same_numbers(client):
    """Deterministic, which is the property the AI call would have removed."""
    first = client.post(reverse("targets:proposals"), payload(), format="json")
    second = client.post(reverse("targets:proposals"), payload(), format="json")

    assert first.data == second.data


# --- validation, and the 500 it prevents -------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("age", 12),
        ("age", 101),
        ("height_in", 35),
        ("height_in", 97),
        ("sex", "unspecified"),
        ("goal", "recomposition"),
        ("activity", "athlete"),
    ],
)
def test_an_answer_outside_its_bounds_is_refused(client, field, value):
    response = client.post(reverse("targets:proposals"), payload(**{field: value}), format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data


@pytest.mark.parametrize(
    "weight",
    [MINIMUM_SUPPORTED_WEIGHT_LB - 1, MAXIMUM_SUPPORTED_WEIGHT_LB + 1],
)
def test_a_weight_outside_the_supported_band_is_a_400_not_a_500(client, weight):
    """The precondition, enforced where it turns into a readable error.

    Outside 85 to 500 lb the suggested calorie floor and ceiling cross and
    `Range.__post_init__` raises `ValueError`. Without this check that is an
    unhandled exception and a 500, for an input a user can type.
    """
    response = client.post(
        reverse("targets:proposals"), payload(weight_lb=str(weight)), format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "weight_lb" in response.data


@pytest.mark.parametrize("weight", [MINIMUM_SUPPORTED_WEIGHT_LB, MAXIMUM_SUPPORTED_WEIGHT_LB])
def test_both_ends_of_the_supported_band_are_accepted(client, weight):
    """Boundaries asserted on the inside as well as the outside.

    An off-by-one here refuses a real user at exactly 85 lb, and only a test on
    the boundary itself would notice.
    """
    response = client.post(
        reverse("targets:proposals"), payload(weight_lb=str(weight)), format="json"
    )

    assert response.status_code == status.HTTP_200_OK


def test_a_missing_answer_is_refused(client):
    body = payload()
    del body["activity"]

    response = client.post(reverse("targets:proposals"), body, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "activity" in response.data


def test_every_missing_answer_is_reported_at_once(client):
    """Same reasoning as the clamp's. Fixing one at a time makes a caller guess."""
    response = client.post(reverse("targets:proposals"), {}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert set(response.data) == {"age", "sex", "height_in", "weight_lb", "goal", "activity"}


def test_the_proposal_can_be_accepted_by_posting_it_back(client, user):
    """The round trip the two endpoints exist to make.

    Worth one test, because the split between them is a design decision: the
    proposal is computed and the version is created, and nothing enforces that
    the numbers a user accepts are the ones they were offered.
    """
    proposal = client.post(reverse("targets:proposals"), payload(), format="json")

    accepted = client.post(
        reverse("targets:list-create"),
        {**proposal.data["targets"], "effective_from": "2026-08-31"},
        format="json",
    )

    assert accepted.status_code == status.HTTP_201_CREATED
    user.refresh_from_db()
    assert user.onboarding_completed is True
    current = TargetVersion.objects.current(user)
    assert current is not None
    assert current.calories == 2059


def test_a_weight_with_cents_is_accepted(client):
    """The client sends a decimal, because `current_weight_lb` stores two places."""
    response = client.post(reverse("targets:proposals"), payload(weight_lb="155.50"), format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.data["targets"]["protein_g"] == round(Decimal("155.50"))
