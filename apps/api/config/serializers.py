"""
Project-level serializers.

These cover system/meta endpoints that don't belong to a domain app
(`accounts`, `targets`, `logging`, `ai`). Domain serializers live with their app.
"""

from rest_framework import serializers


class PingSerializer(serializers.Serializer):
    """Response body for the API liveness probe.

    Fields are declared explicitly (never `fields = "__all__"`) so the emitted
    OpenAPI schema is precise enough to generate useful client types from.
    """

    status = serializers.CharField(
        help_text="Always `ok` when the API is reachable. Proves the CI drift check.",
    )
    version = serializers.CharField(
        help_text="API version string, mirroring SPECTACULAR_SETTINGS['VERSION'].",
    )
    timestamp = serializers.DateTimeField(
        help_text="Server time in UTC (ISO 8601) when the request was handled.",
    )
