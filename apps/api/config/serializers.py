"""
Project-level serializers.

These cover system/meta endpoints that don't belong to a domain app
(`accounts`, `targets`, `logging`, `ai`). Domain serializers live with their app.
"""

from rest_framework import serializers

# The health check's two states, as a module-level constant because
# SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"] imports it by path to name the
# emitted enum component. Inlining the list in the field would leave the
# component named `StatusEnum` — generic enough that the next serializer with a
# `status` field collides with it and drf-spectacular renames one, churning the
# generated client for an unrelated change.
HEALTH_STATUS_CHOICES = ["ok", "unhealthy"]


class PingSerializer(serializers.Serializer):
    """Response body for the API liveness probe.

    Fields are declared explicitly (never `fields = "__all__"`) so the emitted
    OpenAPI schema is precise enough to generate useful client types from.
    """

    status = serializers.CharField(
        help_text="Always `ok` when the API is reachable.",
    )
    version = serializers.CharField(
        help_text="API version string, mirroring SPECTACULAR_SETTINGS['VERSION'].",
    )
    timestamp = serializers.DateTimeField(
        help_text="Server time in UTC (ISO 8601) when the request was handled.",
    )


class HealthSerializer(serializers.Serializer):
    """Response body for the deployment health check.

    Distinct from `PingSerializer` on purpose. Ping answers "is the process
    up?"; health answers "can this process actually serve a request?", which
    means proving the database is reachable. They report different things and a
    shared shape would blur that.
    """

    status = serializers.ChoiceField(
        choices=HEALTH_STATUS_CHOICES,
        help_text=(
            "`ok` when every dependency check passed, `unhealthy` otherwise. "
            "An `unhealthy` body is always served with HTTP 503, never 200."
        ),
    )
    database = serializers.BooleanField(
        help_text=(
            "Whether a real query against the default database succeeded. This "
            "is an executed round-trip, not a check that settings are present."
        ),
    )
    version = serializers.CharField(
        help_text="API version string, mirroring SPECTACULAR_SETTINGS['VERSION'].",
    )
    timestamp = serializers.DateTimeField(
        help_text="Server time in UTC (ISO 8601) when the check was performed.",
    )
