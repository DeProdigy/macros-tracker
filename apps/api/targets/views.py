"""Views for `/api/targets/`.

Thin by design. Every rule that matters lives in `services.py` and the
serializers: the clamp, the future-date refusal, and the profile lookup. These
parse, delegate, and serialize.

Plain `APIView` rather than `ListCreateAPIView`, matching `uploads` and
`accounts`. The generic saves four lines and hides which method does what behind
a base class, and `@extend_schema` has to be spelled out either way.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from targets.models import TargetVersion
from targets.serializers import TargetVersionCreateSerializer, TargetVersionSerializer


class TargetVersionListCreateView(APIView):
    """The collection. Read it, or add to it.

    **There is deliberately no `history/` route.** Targets are append-only, so
    this collection *is* the history, and MAC-44's history screen reads it. Two
    URLs for one list is the mistake the 20 Aug 2026 route audit removed, and it
    survives only because "history" is what the screen is called.

    **No `PATCH` and no `PUT` either.** Editing writes a new version through this
    same `POST`, differing only in `source`. That is the append-only model
    showing through the URL design rather than hiding behind it.
    """

    @extend_schema(
        operation_id="listTargets",
        summary="Every target version, newest first",
        tags=["targets"],
        responses={
            status.HTTP_200_OK: TargetVersionSerializer(many=True),
            status.HTTP_401_UNAUTHORIZED: None,
        },
    )
    def get(self, request: Request) -> Response:
        versions = TargetVersion.objects.for_user(request.user)
        return Response(TargetVersionSerializer(versions, many=True).data)

    @extend_schema(
        operation_id="createTarget",
        summary="Set new targets",
        tags=["targets"],
        request=TargetVersionCreateSerializer,
        responses={
            status.HTTP_201_CREATED: TargetVersionSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = TargetVersionCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        version = serializer.save()
        return Response(TargetVersionSerializer(version).data, status=status.HTTP_201_CREATED)


class CurrentTargetVersionView(APIView):
    """The version in effect now.

    A named singleton, which the route conventions allow: the client cannot
    address this row by id, and "the version in effect now" is state the server
    genuinely owns. Unlike `today`, which doc 07 rejected for the same test.

    **404 when the user has no versions**, not an empty 200. A user without
    targets is a supported state rather than an error, but the resource genuinely
    does not exist, and a 200 with an empty body makes every caller null-check
    something that claims to be a target.
    """

    @extend_schema(
        operation_id="getCurrentTarget",
        summary="The targets in effect now",
        tags=["targets"],
        responses={
            status.HTTP_200_OK: TargetVersionSerializer,
            status.HTTP_401_UNAUTHORIZED: None,
            status.HTTP_404_NOT_FOUND: None,
        },
    )
    def get(self, request: Request) -> Response:
        version = TargetVersion.objects.current(request.user)
        if version is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(TargetVersionSerializer(version).data)
