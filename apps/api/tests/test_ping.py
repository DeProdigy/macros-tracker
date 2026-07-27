"""Tests for the project-level ping endpoint and the schema it emits.

Ping is the demo endpoint proving the typed contract chain (MAC-15), so these
cover both the HTTP behaviour and the OpenAPI output the client is generated
from. The schema assertions are the ones that matter long-term: if the
operationId or component shape drifts, the generated hook silently changes name
or type and every call site breaks at once.

None of these touch the database, so none take `django_db`.
"""

from datetime import datetime

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    """Deliberately not named `client`: that would shadow pytest-django's own
    fixture, and a later test wanting the plain Django test client would get
    DRF's APIClient instead without anything saying so."""
    return APIClient()


# --- HTTP behaviour ---------------------------------------------------------


def test_ping_returns_200_unauthenticated(api_client: APIClient):
    """The project default is IsAuthenticated; ping must opt out of it."""
    response = api_client.get(reverse("ping"))

    assert response.status_code == status.HTTP_200_OK


def test_ping_returns_exactly_the_documented_fields(api_client: APIClient):
    """Guards the contract: extra or missing keys mean the generated type lies."""
    response = api_client.get(reverse("ping"))

    assert set(response.json()) == {"status", "version", "timestamp"}


def test_ping_reports_ok_status(api_client: APIClient):
    response = api_client.get(reverse("ping"))

    assert response.json()["status"] == "ok"


def test_ping_reports_the_configured_api_version(api_client: APIClient):
    """Pins the response to the same literal the OpenAPI document is stamped
    with. Asserting only non-emptiness would let the endpoint and the schema
    drift to different versions without failing."""
    response = api_client.get(reverse("ping"))

    assert response.json()["version"] == settings.SPECTACULAR_SETTINGS["VERSION"]


def test_ping_version_matches_the_emitted_schema_version(api_client: APIClient, schema: dict):
    """The client is generated from the schema's version; the endpoint reports
    its own. This is the assertion that catches them diverging."""
    response = api_client.get(reverse("ping"))

    assert response.json()["version"] == schema["info"]["version"]


def test_ping_timestamp_is_parseable_and_timezone_aware(api_client: APIClient):
    """The generated TS type is `string`; it still has to be a real datetime."""
    response = api_client.get(reverse("ping"))

    parsed = datetime.fromisoformat(response.json()["timestamp"])

    assert parsed.tzinfo is not None


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_ping_rejects_non_get_methods(api_client: APIClient, method: str):
    """Only GET is declared in the schema, so only GET may be routed."""
    response = getattr(api_client, method)(reverse("ping"))

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# --- Emitted schema ---------------------------------------------------------


@pytest.fixture
def schema() -> dict:
    """The in-memory OpenAPI document, as `manage.py spectacular` would emit it."""
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def test_schema_uses_the_explicit_operation_id(schema: dict):
    """Drives the generated hook name (`usePing`). Auto-generated ids churn it."""
    assert schema["paths"]["/api/ping/"]["get"]["operationId"] == "ping"


def test_schema_ping_component_declares_all_fields(schema: dict):
    """`fields = "__all__"` or a vague serializer would erode this."""
    properties = schema["components"]["schemas"]["Ping"]["properties"]

    assert set(properties) == {"status", "version", "timestamp"}


def test_schema_marks_ping_fields_required(schema: dict):
    """Optional fields generate `T | undefined` and defeat compile-time safety."""
    component = schema["components"]["schemas"]["Ping"]

    assert set(component["required"]) == {"status", "version", "timestamp"}


def test_schema_types_timestamp_as_date_time(schema: dict):
    properties = schema["components"]["schemas"]["Ping"]["properties"]

    assert properties["timestamp"]["type"] == "string"
    assert properties["timestamp"]["format"] == "date-time"


def test_schema_does_not_require_auth_for_ping(schema: dict):
    """An empty security requirement is how "no auth needed" is expressed."""
    assert {} in schema["paths"]["/api/ping/"]["get"]["security"]
