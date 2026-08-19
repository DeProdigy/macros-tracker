"""Views for the uploads app.

Thin by design — the signing logic and every validation that matters live in
services.py. These views parse, delegate, and serialize.
"""

from typing import Any, cast

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from uploads import services
from uploads.serializers import (
    PresignUploadRequestSerializer,
    PresignUploadResponseSerializer,
)


class PresignUploadView(APIView):
    """Authorise a direct-to-R2 photo upload.

    Inherits the project-wide IsAuthenticated default deliberately — it does not
    opt out the way ping and health do. An unauthenticated presign endpoint is
    an open write handle to the bucket for anyone who finds the URL, and the
    object key is derived from the requesting user, so there is no sensible key
    to issue without one.
    """

    @extend_schema(
        # Explicit, so the generated hook is `usePresignUpload` rather than
        # `useApiUploadsPresignCreate`. Renaming later churns every call site.
        operation_id="presignUpload",
        summary="Authorise a direct photo upload",
        description=(
            "Returns a short-lived presigned PUT URL and the object key the "
            "upload will land at.\n\n"
            "The client uploads straight to object storage rather than through "
            "this API, so a slow mobile connection never occupies a server "
            "worker. The declared content type and length are signed into the "
            "URL: the subsequent PUT must match both exactly or storage rejects "
            "it.\n\n"
            "Store the returned `key` against the entry. The URL expires; the "
            "key does not."
        ),
        tags=["uploads"],
        request=PresignUploadRequestSerializer,
        responses={
            status.HTTP_200_OK: PresignUploadResponseSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
        },
        examples=[
            OpenApiExample(
                "A 2MB JPEG",
                summary="Typical request",
                description="What the mobile client sends before uploading a camera photo.",
                value={"content_type": "image/jpeg", "content_length": 2097152},
                request_only=True,
            ),
            OpenApiExample(
                "Signed authorisation",
                summary="Successful response",
                description=(
                    "`url` is a bearer credential valid for `expires_in` seconds. "
                    "`key` is what gets persisted."
                ),
                value={
                    "url": "https://<account>.r2.cloudflarestorage.com/bucket/entries/1/...",
                    "key": "entries/1/2f1c9e04-0d5c-4a51-9f0a-3b7c2e6a1d88.jpg",
                    "expires_in": 300,
                    "max_bytes": 10485760,
                },
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        request_serializer = PresignUploadRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        # django-stubs types `.pk` as int | None because AnonymousUser has no
        # primary key. This view does not opt out of the project's
        # IsAuthenticated default, so by the time it runs the user is a saved
        # row and pk is set. Narrowed rather than asserted: `assert` is stripped
        # under `python -O`, which would make the guarantee vanish in exactly
        # the environment that matters.
        user_id = cast(int, request.user.pk)

        presigned = services.presign_upload(
            user_id=user_id,
            content_type=request_serializer.validated_data["content_type"],
            content_length=request_serializer.validated_data["content_length"],
        )

        response_serializer = PresignUploadResponseSerializer(
            {
                "url": presigned.url,
                "key": presigned.key,
                "expires_in": presigned.expires_in,
                "max_bytes": presigned.max_bytes,
            }
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)
