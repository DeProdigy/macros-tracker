"""Tests for the deployment health check and the schema it emits.

Health is what Railway probes to decide whether an instance takes traffic
(MAC-18), so the assertions that matter most are the failure ones: a check that
cannot go red is worth nothing, and the only way to know it can is to break the
database and watch it. Those tests patch the connection rather than stopping
Postgres, so they stay hermetic.

The schema assertions mirror the ping suite's rationale — the generated client
is built from this document, so a drifting operationId or component shape
silently renames a hook or loosens a type.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import DatabaseError, OperationalError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    """Not named `client`: that would shadow pytest-django's own fixture."""
    return APIClient()


@pytest.fixture
def unreachable_database():
    """Make the health check's `SELECT 1` fail the way a real outage does.

    Patches the module-level `connections` the view imported, so only the health
    check is affected and the test database stays usable for everything else.
    `OperationalError` is what psycopg raises for a refused connection or a
    dropped socket — the realistic failure — and it subclasses `DatabaseError`,
    which is what the view catches.
    """
    with patch("config.views.connections") as mock_connections:
        mock_connections["default"].cursor.side_effect = OperationalError(
            "could not connect to server: Connection refused"
        )
        yield mock_connections


# --- Healthy path -----------------------------------------------------------


@pytest.mark.django_db
def test_health_returns_200_when_the_database_is_reachable(api_client: APIClient):
    response = api_client.get(reverse("health"))

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_health_returns_200_unauthenticated(api_client: APIClient):
    """The project default is IsAuthenticated. A platform probe carries no
    credentials, so an auth failure here would be reported as an outage."""
    response = api_client.get(reverse("health"))

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_health_returns_exactly_the_documented_fields(api_client: APIClient):
    """Guards the contract: extra or missing keys mean the generated type lies."""
    response = api_client.get(reverse("health"))

    assert set(response.json()) == {"status", "database", "version", "timestamp"}


@pytest.mark.django_db
def test_health_reports_ok_status_when_healthy(api_client: APIClient):
    assert api_client.get(reverse("health")).json()["status"] == "ok"


@pytest.mark.django_db
def test_health_reports_database_true_when_healthy(api_client: APIClient):
    assert api_client.get(reverse("health")).json()["database"] is True


@pytest.mark.django_db
def test_health_reports_the_configured_api_version(api_client: APIClient):
    """Pins the response to the same literal the OpenAPI document is stamped
    with, so the endpoint and the schema cannot drift to different versions."""
    response = api_client.get(reverse("health"))

    assert response.json()["version"] == settings.SPECTACULAR_SETTINGS["VERSION"]


@pytest.mark.django_db
def test_health_timestamp_is_parseable_and_timezone_aware(api_client: APIClient):
    """The generated TS type is `string`; it still has to be a real datetime."""
    parsed = datetime.fromisoformat(api_client.get(reverse("health")).json()["timestamp"])

    assert parsed.tzinfo is not None


# --- Unhealthy path ---------------------------------------------------------
#
# The reason this endpoint exists instead of reusing /api/ping/. If none of
# these can fail, the check is decorative.


def test_health_returns_503_when_the_database_is_unreachable(
    api_client: APIClient, unreachable_database
):
    """503, not 200-with-a-sad-body: the status code is the only part Railway
    reads when deciding whether to route traffic to this instance."""
    response = api_client.get(reverse("health"))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_health_reports_unhealthy_status_when_the_database_is_unreachable(
    api_client: APIClient, unreachable_database
):
    response = api_client.get(reverse("health"))

    assert response.json()["status"] == "unhealthy"


def test_health_reports_database_false_when_the_database_is_unreachable(
    api_client: APIClient, unreachable_database
):
    response = api_client.get(reverse("health"))

    assert response.json()["database"] is False


def test_health_keeps_the_documented_shape_when_unhealthy(
    api_client: APIClient, unreachable_database
):
    """The failure body is the same component as the success body. A client
    generated from the schema must be able to parse both."""
    response = api_client.get(reverse("health"))

    assert set(response.json()) == {"status", "database", "version", "timestamp"}


def test_health_does_not_propagate_the_database_error(api_client: APIClient, unreachable_database):
    """A health check that 500s is indistinguishable from the outage it exists
    to report — the exception must be caught and turned into a 503."""
    response = api_client.get(reverse("health"))

    assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR


def test_health_logs_the_failure_cause(api_client: APIClient, unreachable_database, caplog):
    """A bare 503 with no traceback leaves nothing to debug from in Railway's
    logs, which is the only place this failure is ever observed."""
    api_client.get(reverse("health"))

    assert any(record.levelname == "ERROR" for record in caplog.records)
    assert "could not connect to server" in caplog.text


def test_health_catches_database_errors_other_than_connection_refused(api_client: APIClient):
    """The view catches `DatabaseError`, the base class — not just the
    connection-refused subclass. A read-only or out-of-connections database is
    equally unable to serve traffic and must also report unhealthy."""
    with patch("config.views.connections") as mock_connections:
        mock_connections["default"].cursor.side_effect = DatabaseError("too many clients")

        response = api_client.get(reverse("health"))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["database"] is False


def test_health_reports_unhealthy_when_the_query_itself_fails(api_client: APIClient):
    """The failure need not be at connect time. Patching the cursor's
    `execute` covers a connection that opens and then dies mid-statement."""
    with patch("config.views.connections") as mock_connections:
        cursor = mock_connections["default"].cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = OperationalError("server closed the connection")

        response = api_client.get(reverse("health"))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["status"] == "unhealthy"


# --- Method routing ---------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_health_rejects_non_get_methods(api_client: APIClient, method: str):
    """Only GET is declared in the schema, so only GET may be routed."""
    response = getattr(api_client, method)(reverse("health"))

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# --- Emitted schema ---------------------------------------------------------


@pytest.fixture
def schema() -> dict:
    """The in-memory OpenAPI document, as `manage.py spectacular` would emit it."""
    from drf_spectacular.generators import SchemaGenerator

    return SchemaGenerator().get_schema(request=None, public=True)


def test_schema_uses_the_explicit_operation_id(schema: dict):
    """Drives the generated hook name (`useHealth`). Auto-generated ids churn it."""
    assert schema["paths"]["/api/health/"]["get"]["operationId"] == "health"


def test_schema_health_component_declares_all_fields(schema: dict):
    properties = schema["components"]["schemas"]["Health"]["properties"]

    assert set(properties) == {"status", "database", "version", "timestamp"}


def test_schema_marks_health_fields_required(schema: dict):
    """Optional fields generate `T | undefined` and defeat compile-time safety."""
    component = schema["components"]["schemas"]["Health"]

    assert set(component["required"]) == {"status", "database", "version", "timestamp"}


def test_schema_constrains_status_to_the_two_real_values(schema: dict):
    """`status` is a ChoiceField so the generated type is a union, not `string`."""
    assert set(schema["components"]["schemas"]["HealthStatusEnum"]["enum"]) == {
        "ok",
        "unhealthy",
    }


def test_schema_names_the_status_enum_explicitly(schema: dict):
    """Pinned via ENUM_NAME_OVERRIDES. Left to drf-spectacular this component is
    named `StatusEnum` after the field, which the next serializer with a
    `status` field would collide with — renaming one of them and churning the
    generated client over a change that has nothing to do with health."""
    status_property = schema["components"]["schemas"]["Health"]["properties"]["status"]

    # Wrapped in `allOf` rather than a bare `$ref` because the field carries a
    # description; a lone `$ref` may not have sibling keys in OpenAPI 3.0.
    assert status_property["allOf"] == [{"$ref": "#/components/schemas/HealthStatusEnum"}]
    assert "StatusEnum" not in schema["components"]["schemas"]


def test_schema_types_database_as_boolean(schema: dict):
    properties = schema["components"]["schemas"]["Health"]["properties"]

    assert properties["database"]["type"] == "boolean"


def test_schema_documents_the_503_response(schema: dict):
    """The unhealthy response is part of the contract, not an undocumented
    surprise — a client generated without it cannot type the failure case."""
    responses = schema["paths"]["/api/health/"]["get"]["responses"]

    assert "503" in responses


def test_schema_does_not_require_auth_for_health(schema: dict):
    """An empty security requirement is how "no auth needed" is expressed."""
    assert {} in schema["paths"]["/api/health/"]["get"]["security"]
