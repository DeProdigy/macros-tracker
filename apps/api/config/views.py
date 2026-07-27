"""
Project-level views.

System/meta endpoints that aren't owned by a domain app. Views stay thin —
anything with real logic belongs in the owning app's `services.py`.
"""

from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.serializers import PingSerializer

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
