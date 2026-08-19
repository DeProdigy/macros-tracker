"""Serializers for the uploads app.

Fields are declared explicitly (never `fields = "__all__"`) so the emitted
OpenAPI schema is precise enough to generate useful client types from.
"""

from django.conf import settings
from rest_framework import serializers


class PresignUploadRequestSerializer(serializers.Serializer):
    """What the client must state before an upload is authorised.

    Both fields are required. Letting either default would mean signing a URL
    whose constraints the client never committed to, which is the same as not
    constraining it.
    """

    content_type = serializers.CharField(
        help_text=(
            "MIME type of the file about to be uploaded. Must be one of the "
            "supported image types; the PUT is rejected if it does not match."
        ),
    )
    content_length = serializers.IntegerField(
        min_value=1,
        help_text=(
            "Exact size in bytes of the file about to be uploaded. Signed into "
            "the URL, so the PUT must send precisely this many bytes."
        ),
    )


class PresignUploadResponseSerializer(serializers.Serializer):
    """The signed authorisation handed back to the client."""

    url = serializers.URLField(
        help_text=(
            "Presigned S3 PUT URL. Treat as a credential: anyone holding it can "
            "upload to this key until it expires."
        ),
    )
    key = serializers.CharField(
        help_text=(
            "Object key the upload will land at. Store this against the entry — "
            "it is the durable identifier, whereas the URL expires."
        ),
    )
    expires_in = serializers.IntegerField(
        help_text="Seconds until the URL stops being accepted.",
    )
    max_bytes = serializers.IntegerField(
        help_text=(
            "Server-side upload ceiling, echoed so a client can fail fast "
            "locally instead of discovering it on a rejected PUT."
        ),
    )


def supported_upload_types() -> list[str]:
    """The allowlist, for schema documentation and error messages."""
    return sorted(settings.R2_ALLOWED_UPLOAD_TYPES)
