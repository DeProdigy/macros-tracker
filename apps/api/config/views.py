"""
Project-level views.

System/meta endpoints that aren't owned by a domain app. Views stay thin —
anything with real logic belongs in the owning app's `services.py`.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db import DatabaseError, connections
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.serializers import HealthSerializer, PingSerializer

logger = logging.getLogger(__name__)

# Single source of truth for the API version. SPECTACULAR_SETTINGS already owns
# it (it stamps the emitted OpenAPI document), so the endpoint reads it from
# there rather than repeating the literal. Duplicating it would let the response
# and the schema drift apart on the first version bump, silently — the response
# would claim one version while the contract clients generate from claims
# another.
# `str()` because Django types settings dicts as `dict[str, object]`; the value
# is a string by construction in base.py.
API_VERSION: str = str(settings.SPECTACULAR_SETTINGS["VERSION"])


class PingView(APIView):
    """Unauthenticated liveness probe.

    Exists to prove the typed contract pipeline end to end: this view's
    serializer becomes an OpenAPI component, which Orval turns into the
    `usePing` hook that apps/mobile calls.
    """

    # The project default is IsAuthenticated. Ping must be callable before a
    # user exists, so it opts out explicitly.
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        # Set explicitly: this becomes the generated hook name (`usePing`).
        # Letting it auto-generate yields names like `useApiPingRetrieve`, and
        # renaming later churns every call site.
        operation_id="ping",
        summary="API liveness probe",
        description=(
            "Returns a small fixed-shape payload confirming the API is reachable "
            "and able to serialize a response. Requires no authentication and "
            "touches no database, so it is safe to call from an unauthenticated "
            "client and as a container health check."
        ),
        tags=["system"],
        responses={status.HTTP_200_OK: PingSerializer},
        examples=[
            OpenApiExample(
                "Healthy",
                summary="Normal response",
                description="What a reachable API returns.",
                value={
                    "status": "ok",
                    "version": API_VERSION,
                    "timestamp": "2026-07-23T12:34:56Z",
                },
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PingSerializer(
            {
                "status": "ok",
                "version": API_VERSION,
                "timestamp": datetime.now(UTC),
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


def _database_is_reachable() -> bool:
    """Execute a trivial query against the default database.

    The point is the round-trip. Checking that `DATABASE_URL` parses, or that a
    connection object exists, proves nothing — Django connects lazily, so a
    totally unreachable database looks fine until something actually queries it.
    `SELECT 1` is the cheapest statement that forces the connection open and
    waits for the server to answer.

    Returns False rather than raising: the caller turns this into a status code,
    and a health check that 500s is indistinguishable from the outage it exists
    to report.
    """
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        # Logged at exception level so the traceback lands in Railway's logs.
        # Without it the only signal is a 503 with no cause attached.
        logger.exception("Health check failed: database unreachable")
        return False
    return True


class HealthView(APIView):
    """Deployment health check probed by Railway.

    Separate from `PingView` because they answer different questions. Ping asks
    whether the process is up and can serialize a response; health asks whether
    it can serve real traffic, which is a claim about the database too. A health
    check that returns 200 without touching its dependencies reports green while
    every actual request fails — so this one runs a query.
    """

    # Probed by the platform before any user exists, and an auth failure would
    # be reported as an outage. Same opt-out as PingView.
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        # Explicit, so the generated hook is `useHealth` rather than
        # `useApiHealthRetrieve`. Renaming later churns every call site.
        operation_id="health",
        summary="Deployment health check",
        description=(
            "Reports whether the API can serve traffic. Unlike `/api/ping/`, this "
            "executes a real query against the database and returns HTTP 503 if "
            "that query fails, so an orchestrator can pull the instance out of "
            "rotation. Requires no authentication.\n\n"
            "Intended for platform health probes rather than for clients."
        ),
        tags=["system"],
        responses={
            status.HTTP_200_OK: HealthSerializer,
            status.HTTP_503_SERVICE_UNAVAILABLE: HealthSerializer,
        },
        examples=[
            OpenApiExample(
                "Healthy",
                summary="Database reachable",
                description="Every dependency check passed; the instance can serve traffic.",
                value={
                    "status": "ok",
                    "database": True,
                    "version": API_VERSION,
                    "timestamp": "2026-07-23T12:34:56Z",
                },
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
            OpenApiExample(
                "Unhealthy",
                summary="Database unreachable",
                description=(
                    "The process is running but its query failed. Served with 503 so "
                    "the platform treats the instance as unavailable."
                ),
                value={
                    "status": "unhealthy",
                    "database": False,
                    "version": API_VERSION,
                    "timestamp": "2026-07-23T12:34:56Z",
                },
                response_only=True,
                status_codes=[str(status.HTTP_503_SERVICE_UNAVAILABLE)],
            ),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        database_ok = _database_is_reachable()

        serializer = HealthSerializer(
            {
                "status": "ok" if database_ok else "unhealthy",
                "database": database_ok,
                "version": API_VERSION,
                "timestamp": datetime.now(UTC),
            }
        )
        return Response(
            serializer.data,
            status=(status.HTTP_200_OK if database_ok else status.HTTP_503_SERVICE_UNAVAILABLE),
        )
