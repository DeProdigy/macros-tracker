"""Views for `/api/targets/`.

Thin by design. Every rule that matters lives in `services.py` and the
serializers: the clamp, the future-date refusal, and the profile lookup. These
parse, delegate, and serialize.

Plain `APIView` rather than `ListCreateAPIView`, matching `uploads` and
`accounts`. The generic saves four lines and hides which method does what behind
a base class, and `@extend_schema` has to be spelled out either way.
"""

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from targets import services
from targets.models import TargetVersion
from targets.serializers import (
    TargetProposalRequestSerializer,
    TargetProposalSerializer,
    TargetVersionCreateSerializer,
    TargetVersionSerializer,
)
from targets.throttles import TargetProposalThrottle


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


class TargetProposalView(APIView):
    """Six answers in, three numbers and an explanation out.

    **`proposals` is the resource, and it is not named after its caller.**
    Onboarding asks for one, and Settings will ask for another when a user's
    weight changes. Calling this `/api/onboarding/` would have needed renaming
    the moment the second caller appeared, and by then the name is in the
    generated client and every call site.

    **200, not 201.** Nothing addressable is created. The proposal is computed
    and returned, and the user accepts it by posting to `/api/targets/`, which
    is what creates a `TargetVersion`. Whether a proposal is ever persisted is
    an implementation detail the URL must not encode.

    **No AI.** The whole calculation is Mifflin-St Jeor plus an activity
    multiplier, a goal adjustment, and a template. A model call used to sit on
    top of this and was cancelled on 31 Aug 2026: the paragraph it was going to
    write is about numbers this server already computed, so a template reads the
    real values instead of being told about them. See doc 05.
    """

    throttle_classes = [TargetProposalThrottle]

    @extend_schema(
        operation_id="createTargetProposal",
        summary="Work out targets from the six onboarding answers",
        description=(
            "Takes the six onboarding answers and returns proposed daily "
            "calorie, protein, and fiber targets with a plain-English "
            "explanation.\n\n"
            "**Nothing is created or stored.** The response is computed. A user "
            "accepts it by posting the three numbers to `/api/targets/`, which "
            "is where a target version comes from. That is why this returns 200 "
            "rather than 201.\n\n"
            "**Deterministic.** Mifflin-St Jeor for resting burn, an activity "
            "multiplier, then a percentage adjustment for the goal. The same "
            "answers always give the same numbers, no model provider is "
            "involved, and the call costs nothing.\n\n"
            "**Units are pounds and inches**, matching every screen. The server "
            "converts once, where the formula needs metric.\n\n"
            "`baseline` is what the formula produced and `targets` is what "
            "survived the guardrails. They are equal unless `clamped` is true, "
            "and screen 9f shows the pair only when it is."
        ),
        tags=["targets"],
        request=TargetProposalRequestSerializer,
        responses={
            status.HTTP_200_OK: TargetProposalSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
            status.HTTP_429_TOO_MANY_REQUESTS: None,
        },
        examples=[
            OpenApiExample(
                "A 35 year old man cutting",
                summary="Six answers in",
                value={
                    "age": 35,
                    "sex": "male",
                    "height_in": 71,
                    "weight_lb": "155.00",
                    "goal": "cut",
                    "activity": "moderate",
                },
                request_only=True,
            ),
            OpenApiExample(
                "The proposal",
                summary="Inside the guardrails, so baseline and targets agree",
                description=(
                    "`clamped` is false, so screen 9f shows the three numbers and no baseline line."
                ),
                value={
                    "targets": {"calories": 2059, "protein_g": 155, "fiber_g": 29},
                    "baseline": {"calories": 2059, "protein_g": 155, "fiber_g": 29},
                    "clamped": False,
                    "rationale": (
                        "2,059 calories a day. That is 20% below the 2,573 you burn, "
                        "which puts you on track for about 1.0 lb a week. Protein at "
                        "155 g is 1.0 g per pound of body weight, the amount the "
                        "research supports for holding on to muscle while you lose "
                        "fat. Fiber at 29 g follows the US guideline of 14 g per "
                        "1,000 calories, which digestion and appetite both depend on."
                    ),
                },
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = TargetProposalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        proposal = services.propose(serializer.to_answers())

        return Response(TargetProposalSerializer(proposal).data)
