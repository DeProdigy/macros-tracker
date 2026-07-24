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
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def client() -> APIClient:
    return APIClient()


# --- HTTP behaviour ---------------------------------------------------------


def test_ping_returns_200_unauthenticated(client: APIClient):
    """The project default is IsAuthenticated; ping must opt out of it."""
    response = client.get(reverse("ping"))

    assert response.status_code == status.HTTP_200_OK


def test_ping_returns_exactly_the_documented_fields(client: APIClient):
    """Guards the contract: extra or missing keys mean the generated type lies."""
    response = client.get(reverse("ping"))

    assert set(response.json()) == {"status", "version", "timestamp"}


def test_ping_reports_ok_status(client: APIClient):
    response = client.get(reverse("ping"))

    assert response.json()["status"] == "ok"


def test_ping_version_is_a_non_empty_string(client: APIClient):
    response = client.get(reverse("ping"))
    version = response.json()["version"]

    assert isinstance(version, str)
    assert version


def test_ping_timestamp_is_parseable_and_timezone_aware(client: APIClient):
    """The generated TS type is `string`; it still has to be a real datetime."""
    response = client.get(reverse("ping"))

    parsed = datetime.fromisoformat(response.json()["timestamp"])

    assert parsed.tzinfo is not None


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_ping_rejects_non_get_methods(client: APIClient, method: str):
    """Only GET is declared in the schema, so only GET may be routed."""
    response = getattr(client, method)(reverse("ping"))

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
