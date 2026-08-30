"""Views for the accounts app.

Thin by design. Verification lives in services.verify_apple_identity_token and
resolution in services.resolve_apple_user; these views parse, delegate, and
serialize.
"""

from typing import Any, cast

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from accounts import services
from accounts.models import User
from accounts.schema import RequestBodyOnDeleteAutoSchema
from accounts.serializers import (
    SessionCreateSerializer,
    SessionDeleteSerializer,
    SessionRefreshSerializer,
    SessionSerializer,
    UserSerializer,
    UserSettingsSerializer,
)
from accounts.throttles import RefreshThrottle, SignInBurstThrottle, SignInSustainedThrottle


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
                        "timezone": "UTC",
                        "onboarding_completed": False,
                        "sex": "",
                        "current_weight_lb": None,
                        "goal_weight_lb": None,
                        "goal_timeline_weeks": None,
                        "training_days_per_week": None,
                        "dietary_constraints": "",
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


class SessionRefreshView(TokenRefreshView):
    """Exchange a refresh token for a new pair.

    Subclassed rather than routed directly, for two reasons.

    The schema is the first. simplejwt's `TokenRefreshView` carries no
    `@extend_schema`, so `spectacular --fail-on-warn` fails on it and the client
    never generates. The generated hook name is the second: the base view would
    produce `useApiAuthSessionsRefreshCreate`, and an operation id is not
    something to rename after call sites exist.

    The refresh logic itself is inherited, deliberately. Rotation, blacklisting
    the presented token, and the sliding-token variants are simplejwt's problem,
    and reimplementing them here to own the response shape would be a security
    control rewritten for cosmetics.
    """

    # This is the whole reason the endpoint works: it is reached precisely
    # *because* the access token expired, so requiring a valid one to get a new
    # one is a deadlock. Empty authentication_classes then stops
    # SessionAuthentication running a CSRF check against a request that carries
    # no session. Same pair as SessionCreateView and PingView.
    #
    # Empty rather than `[AllowAny]`, which would read the same as the two views
    # above and is what this would say given the choice. simplejwt annotates
    # both attributes as `tuple[()]`, so every spelling of AllowAny is an
    # incompatible assignment under mypy, and two `type: ignore`s to win a
    # naming preference is the wrong trade. An empty permission list means
    # AllowAny to DRF: `get_permissions` returns nothing to check.
    permission_classes = ()
    authentication_classes = ()
    # Unauthenticated, so it is throttled. Not a security control -- a valid
    # refresh token is already a credential and there is nothing to guess -- but
    # every call costs a signature verification and, on success, two writes.
    # See throttles.py for why this one has a single scope where sign-in has two.
    throttle_classes = [RefreshThrottle]

    @extend_schema(
        operation_id="refreshSession",
        summary="Refresh a session",
        description=(
            "Exchanges a valid refresh token for a new access token **and a new "
            "refresh token**. Rotation is on, so the presented refresh token is "
            "blacklisted by this call: store the returned pair and discard the "
            "old one, or the next refresh fails.\n\n"
            "**Requires no authentication, by design.** This endpoint exists "
            "because the access token has expired, so demanding a valid one "
            "here would be a deadlock. The refresh token in the body *is* the "
            "credential.\n\n"
            "A rejected token returns 401 whether it expired, was already "
            "rotated, or was never valid. Reusing a rotated token is the "
            "signature of a stolen credential, and the client's only correct "
            "response to any 401 here is to sign in again."
        ),
        tags=["auth"],
        request=SessionRefreshSerializer,
        responses={
            status.HTTP_200_OK: SessionRefreshSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
            status.HTTP_429_TOO_MANY_REQUESTS: None,
        },
        examples=[
            OpenApiExample(
                "Refresh",
                summary="Present the stored refresh token",
                value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
                request_only=True,
            ),
            OpenApiExample(
                "New pair",
                summary="Successful response",
                description=(
                    "`refresh` differs from the one presented. Overwrite both values in "
                    "the Keychain together."
                ),
                value={
                    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                },
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            # 200, not 201. Nothing addressable was created -- the session
            # already existed and this returns a fresh representation of the
            # credential for it. Compare SessionCreateView, which does create
            # one.
            return super().post(request, *args, **kwargs)
        except User.DoesNotExist as exc:
            # simplejwt looks the token's user up with a bare `.get()`
            # (serializers.py:116 at 5.5.1), so a valid token that outlived its
            # user row raises straight through DRF's exception handler as a 500.
            #
            # A token whose user is gone is a dead credential, not a server
            # fault. 401 matches every other rejected token here, and keeps the
            # description's promise that the client's answer to any 401 on this
            # endpoint is to sign in again.
            #
            # Nothing in the app hard-deletes a user yet. The admin's delete
            # button reaches it today, and MAC-29 is account deletion, so this
            # does not belong in the ticket that inherits it.
            raise AuthenticationFailed("Token is invalid or expired.") from exc


class CurrentSessionView(APIView):
    """Sign out: blacklist the presented refresh token.

    Named singleton. `current` is the one session the caller can address, and it
    has no id of its own for the client to hold.
    """

    # DELETE carries a body here, and drf-spectacular drops request bodies on
    # DELETE by default -- so without this the generated client would have no
    # way to send the refresh token. See the class for why the body is right.
    schema = RequestBodyOnDeleteAutoSchema()

    @extend_schema(
        operation_id="deleteCurrentSession",
        summary="Sign out",
        description=(
            "Blacklists the refresh token in the body, so it can never mint "
            "another access token.\n\n"
            "**The refresh token goes in the body of a DELETE**, which is "
            "unusual and is the only option there is: blacklisting an access "
            "token is not a thing that exists in this scheme. Nothing on the "
            "access path consults a blacklist, which is also why signing out "
            "does not invalidate the access token the client is holding — that "
            "one stays valid until it expires, within 15 minutes. Discard both "
            "tokens client-side as well.\n\n"
            "Authenticated, and the token must belong to the caller. Signing "
            "out is idempotent from the client's point of view: an already "
            "blacklisted or malformed token returns 400 and the client should "
            "clear its storage regardless."
        ),
        tags=["auth"],
        request=SessionDeleteSerializer,
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
        },
        examples=[
            OpenApiExample(
                "Sign out",
                summary="Present the stored refresh token",
                value={"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
                request_only=True,
            ),
        ],
    )
    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = SessionDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
        except TokenError as exc:
            # Expired, already blacklisted, or never ours. All the same answer:
            # there is nothing left to revoke and the client's next step is
            # identical in every case.
            raise ValidationError({"refresh": "Token is invalid or expired."}) from exc

        # Ownership check. Without it, any authenticated user can blacklist any
        # refresh token they can get hold of, which is a denial of service on
        # somebody else's session dressed up as a sign-out.
        #
        # Compared as strings on purpose: simplejwt stringifies the id when it
        # mints the claim, so `token.payload["user_id"]` is "42" and
        # `request.user.pk` is 42. A `!=` between those is always True, and the
        # bug it produces is the worst shape available -- every sign-out fails
        # with "not your token", including the ordinary one.
        owner_id = str(getattr(request.user, api_settings.USER_ID_FIELD))
        if str(token.payload.get(api_settings.USER_ID_CLAIM)) != owner_id:
            raise ValidationError({"refresh": "Token is invalid or expired."})

        token.blacklist()

        # 204: a delete succeeded and there is nothing to say about it.
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    """Read or update the signed-in user.

    Named singleton again, and the exception the route conventions allow: the
    client cannot address itself by id, and the server genuinely owns which user
    a bearer token resolves to.

    `APIView` rather than `RetrieveUpdateAPIView`. The generic view is a better
    fit for everything except one detail -- it also routes `PUT`, and a full
    replace cannot tell "field omitted" from "field cleared". Three explicit
    methods beat a fourth that has to be suppressed.

    `DELETE` is here rather than at a URL of its own because it acts on this
    same row. `GET /api/auth/me/` beside `DELETE /api/auth/account/` was one
    entity under two names, which is what the 20 Aug 2026 route audit removed.
    """

    @extend_schema(
        operation_id="getCurrentUser",
        summary="Read the signed-in user",
        description=(
            "Returns the user the bearer token resolves to. This is how the "
            "client learns who it is signed in as after a cold start, and "
            "`onboarding_completed` is what it routes on: false sends the user "
            "to onboarding, true to Today.\n\n"
            "401 when the token is missing, malformed, or expired — which the "
            "client should treat as 'refresh, then retry once'."
        ),
        tags=["users"],
        responses={
            status.HTTP_200_OK: UserSerializer,
            status.HTTP_401_UNAUTHORIZED: None,
        },
        examples=[
            OpenApiExample(
                "Current user",
                summary="A user partway through settings",
                description=(
                    "The four settings fields are null or empty until the user fills "
                    "them in, which most never will."
                ),
                value={
                    "id": 1,
                    "email": "user@privaterelay.appleid.com",
                    "name": "Alex Hint",
                    "timezone": "Europe/London",
                    "onboarding_completed": True,
                    "sex": "male",
                    "current_weight_lb": "192.00",
                    "goal_weight_lb": "173.00",
                    "goal_timeline_weeks": 12,
                    "training_days_per_week": 4,
                    "dietary_constraints": "",
                },
                response_only=True,
                status_codes=[str(status.HTTP_200_OK)],
            ),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        operation_id="updateCurrentUser",
        summary="Update the signed-in user's settings",
        description=(
            "Partial update of the settings doc 05 moved out of onboarding: "
            "goal weight, timeline, training days, and dietary constraints — "
            "plus the timezone the client refreshes on launch.\n\n"
            "**Partial.** An omitted field is left untouched; an explicit null "
            "clears it back to unanswered. That distinction is the reason this "
            "is `PATCH` and not `PUT`: a full replace cannot tell the two "
            "apart.\n\n"
            "Only these fields are writable. `email` and `name` come from Apple "
            "at sign-in, and `onboarding_completed` is set by completing "
            "onboarding, so none of them are accepted here — sending them is "
            "ignored, not an error. The response is the full user, so the "
            "client can replace its cached copy with one round trip."
        ),
        tags=["users"],
        request=UserSettingsSerializer,
        responses={
            status.HTTP_200_OK: UserSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_401_UNAUTHORIZED: None,
        },
        examples=[
            OpenApiExample(
                "Set a goal",
                summary="Two fields, the rest untouched",
                value={
                    "current_weight_lb": "192.00",
                    "goal_weight_lb": "173.00",
                    "goal_timeline_weeks": 12,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Clear the goal",
                summary="Explicit nulls clear",
                description="Omitting these fields would have left the stored values alone.",
                value={
                    "sex": "",
                    "current_weight_lb": None,
                    "goal_weight_lb": None,
                    "goal_timeline_weeks": None,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Refresh the timezone",
                summary="Sent on app launch",
                value={"timezone": "Europe/London"},
                request_only=True,
            ),
        ],
    )
    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = UserSettingsSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Read shape back, not the write shape. The client asked to change its
        # own user and the useful answer is the whole user -- otherwise it has
        # to follow every PATCH with a GET to refresh its cache.
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        operation_id="deleteCurrentUser",
        summary="Delete the signed-in user's account",
        description=(
            "Deletes the caller's account. Required by both app stores, which "
            "will not ship an app that creates accounts without an in-app way "
            "to remove them.\n\n"
            "**This is reversible.** Signing in again with the same Apple ID "
            "restores the account and its data, as long as the account has not "
            "yet been purged — there is no separate 'undelete' call. The row is "
            "marked deleted rather than destroyed; scheduled destruction is not "
            "implemented yet, so nothing is currently erased.\n\n"
            "Access stops at once. The refresh tokens are blacklisted and the "
            "account is deactivated, so the access token the client is holding "
            "fails on its next use rather than lasting out its 15 minutes. The "
            "client should clear its token storage and route to Welcome.\n\n"
            "Deleting twice changes nothing: the deletion timestamp keeps its "
            "original value. Expect a 401 rather than a second 204, though — "
            "the account is deactivated by then, so authentication rejects the "
            "retry before this endpoint sees it. Either answer means the same "
            "thing to the client, which should clear its tokens and move on."
        ),
        tags=["users"],
        request=None,
        responses={
            status.HTTP_204_NO_CONTENT: None,
            status.HTTP_401_UNAUTHORIZED: None,
        },
    )
    def delete(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # django-stubs types `request.user` as `User | AnonymousUser`. This view
        # does not opt out of the project's IsAuthenticated default, so an
        # anonymous caller never reaches this line. Narrowed rather than
        # asserted: `assert` is stripped under `python -O`, which would drop the
        # guarantee in exactly the environment that matters.
        services.delete_account(cast(User, request.user))

        # 204 whether or not this call is the one that did it. The client asked
        # for the account to be gone; it is gone. A 404 on the second attempt
        # would report a failure for a request that got exactly what it wanted.
        return Response(status=status.HTTP_204_NO_CONTENT)
