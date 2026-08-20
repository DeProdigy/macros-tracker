"""Views for the accounts app.

Thin by design. Verification lives in services.verify_apple_identity_token and
resolution in services.resolve_apple_user; these views parse, delegate, and
serialize.
"""

from typing import Any

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import services
from accounts.serializers import SessionCreateSerializer, SessionSerializer
from accounts.throttles import SignInBurstThrottle, SignInSustainedThrottle


class SessionCreateView(APIView):
    """Sign in with Apple. Creates the account on first use.

    Registration and login are the same call, which is why the resource is a
    session rather than a user: the client does not know, and does not need to
    know, whether this person existed a moment ago.
    """

    # The project default is IsAuthenticated, which would 401 the very request
    # that authenticates the user. Both lines are required -- dropping the
    # authentication_classes override alone leaves SessionAuthentication running
    # CSRF checks against a request that carries no session.
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []
    throttle_classes = [SignInBurstThrottle, SignInSustainedThrottle]

    @extend_schema(
        # Explicit, so the generated hook is `useCreateSession` rather than
        # `useApiAuthSessionsCreate`. Renaming later churns every call site.
        operation_id="createSession",
        summary="Sign in with Apple",
        description=(
            "Exchanges a verified Apple identity token for a user and a JWT "
            "pair. Creates the account when the Apple subject is unknown, so "
            "this one call covers both first-time sign-up and returning "
            "login.\n\n"
            "**Nonce.** Send the *raw* nonce, not the digest. The client sets "
            "`SHA256(nonce)` as lowercase hex on the Apple request and Apple "
            "copies that digest into the token; the server hashes the raw value "
            "to compare. Sending the digest fails verification.\n\n"
            "**Name.** Apple supplies `fullName` on the first authorization "
            "only. Send it when present; omitting it never clears a stored "
            "name. It is not part of the signed token, so it is stored for "
            "display and is not verified.\n\n"
            "**Reactivation.** A previously deleted account is restored "
            "automatically, with no time limit. Once the purge has removed the "
            "row, a sign-in creates a fresh account instead.\n\n"
            "Requires no authentication, and is rate limited by IP. Every "
            "verification failure returns the same 401 regardless of cause."
        ),
        tags=["auth"],
        request=SessionCreateSerializer,
        responses={
            status.HTTP_201_CREATED: SessionSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
            status.HTTP_429_TOO_MANY_REQUESTS: None,
        },
        examples=[
            OpenApiExample(
                "First sign-in",
                summary="New user, name supplied",
                description=(
                    "Apple sends `fullName` only on the first authorization, so this "
                    "shape appears exactly once per user."
                ),
                value={
                    "identity_token": "eyJraWQiOiIxRTZWaW9JYU5JIiwiYWxnIjoiUlMyNTYifQ...",
                    "nonce": "n-0S6_WzA2Mj",
                    "name": "Alex Hint",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Returning sign-in",
                summary="Existing user, no name",
                description=(
                    "Every later sign-in looks like this. Omitting `name` leaves the "
                    "stored value untouched."
                ),
                value={
                    "identity_token": "eyJraWQiOiIxRTZWaW9JYU5JIiwiYWxnIjoiUlMyNTYifQ...",
                    "nonce": "n-0S6_WzA2Mj",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Session",
                summary="Successful response",
                description=(
                    "`created` distinguishes a first run from a returning user. Store "
                    "both tokens in the Keychain; the refresh token rotates on use."
                ),
                value={
                    "user": {
                        "id": 1,
                        "email": "user@privaterelay.appleid.com",
                        "name": "Alex Hint",
                        "onboarding_completed": False,
                        "timezone": "UTC",
                    },
                    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "created": True,
                },
                response_only=True,
                status_codes=[str(status.HTTP_201_CREATED)],
            ),
        ],
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        request_serializer = SessionCreateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        payload = request_serializer.validated_data

        try:
            claims = services.verify_apple_identity_token(
                payload["identity_token"],
                expected_nonce=payload["nonce"],
            )
        except ValidationError as exc:
            # The verifier raises a distinct code per failure so its own tests
            # can prove each check runs. Collapsed to one opaque 401 here: a
            # response that separates "wrong audience" from "bad signature" is
            # a free oracle for anyone probing the endpoint.
            raise services.InvalidAppleCredential() from exc

        resolved = services.resolve_apple_user(claims, name=payload.get("name", ""))
        services.record_authentication(resolved.identity, claims=claims)

        refresh = RefreshToken.for_user(resolved.user)

        response_serializer = SessionSerializer(
            {
                "user": resolved.user,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "created": resolved.created,
            }
        )
        # 201 rather than 200: this created a session. Whether it also created
        # the user is reported in the body, not in the status -- the resource
        # addressed is the session either way.
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
