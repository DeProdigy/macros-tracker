"""Serializers for the accounts app.

Fields are declared explicitly (never `fields = "__all__"`) so the emitted
OpenAPI schema is precise enough to generate useful client types from. An
`__all__` on the user model would also publish `password`, `is_superuser`, and
every permission relation into the mobile app's types.
"""

from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import serializers

from accounts.models import Sex, User

# How far from the server's clock a client-sent `onboarding_skipped_at` may sit.
#
# Same constant and same reasoning as `targets/serializers.py`'s
# `MAX_CLIENT_DATE_SKEW`. A phone with a wrong clock, or one that queued the
# write offline, is a real user. A timestamp a year out is a bug or a client
# inventing history, and the field exists to answer "how long ago did they
# skip?" for E5's re-prompt row.
MAX_CLIENT_CLOCK_SKEW = timedelta(days=1)


class SessionCreateSerializer(serializers.Serializer):
    """What the client presents to sign in.

    Both fields are required. The token alone is not enough: without the nonce
    there is nothing to prove this token was minted for *this* sign-in attempt
    rather than captured from an earlier one.
    """

    identity_token = serializers.CharField(
        trim_whitespace=False,
        help_text=(
            "The `identityToken` from ASAuthorizationAppleIDCredential, as a "
            "JWT string. Verified against Apple's published signing keys before "
            "anything else happens."
        ),
    )
    nonce = serializers.CharField(
        trim_whitespace=False,
        help_text=(
            "The **raw** nonce generated for this sign-in, not the digest. The "
            "client sets `SHA256(nonce)` as lowercase hex on the Apple request; "
            "Apple copies that digest into the token verbatim, and the server "
            "hashes this value to compare. Sending the digest here fails."
        ),
    )
    name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text=(
            "Display name, from `fullName` on the credential. Apple supplies it "
            "on the first authorization only and never again, so send it when "
            "present and omit it otherwise — omitting never clears a stored "
            "name. Unverified: Apple puts no name in the identity token, so "
            "this is the client's word and is used for display only."
        ),
    )


class UserSerializer(serializers.ModelSerializer):
    """The signed-in user, as the client is allowed to see them.

    One serializer for the whole read shape, used by `GET /api/users/me/` and
    embedded in the sign-in response. Two serializers describing the same row
    would generate two client types that drift the first time a field is added
    to one of them.

    A ModelSerializer here, and a hand-written Serializer for the request shapes
    below. The difference is what the fields are: these mirror model columns and
    the validators belong on the model, while a refresh token is not a column
    and never will be.

    Every field is read-only. This is the *read* shape; the subset a client may
    write is `UserSettingsSerializer`, and keeping them apart is what stops a
    client from setting `onboarding_completed` on itself.
    """

    # Declared rather than inferred, because the inferred one lies.
    #
    # `sex` is `blank=True, default=""`, so a user who has not answered reads
    # back as `""`. drf-spectacular emits the blank member only for the
    # *writable* serializer, so the `User` schema came out as `SexEnum` and
    # required, and Orval turned that into `readonly sex: SexEnum`. The committed
    # openapi.json disagreed with itself: the sign-in example showed `"sex": ""`,
    # a value its own `User` schema forbade.
    #
    # What that breaks is quiet. A client switches on `user.sex` over `SexEnum`
    # with no default, TypeScript believes the switch is exhaustive, and every
    # user who skipped the question falls through it with nothing raised.
    sex = serializers.ChoiceField(choices=Sex.choices, allow_blank=True, read_only=True)

    class Meta:
        model = User
        # Explicit, never `fields = "__all__"`. An `__all__` on the user model
        # would publish `password`, `is_superuser`, and every permission
        # relation straight into the mobile app's generated types.
        fields = [
            "id",
            "email",
            "name",
            "timezone",
            "onboarding_completed",
            "onboarding_skipped_at",
            "sex",
            "current_weight_lb",
            "goal_weight_lb",
            "goal_timeline_weeks",
            "training_days_per_week",
            "dietary_constraints",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "email": {
                "help_text": (
                    "May be null: Apple does not guarantee an email, and may "
                    "supply a private relay address rather than a real one."
                )
            },
            "name": {"help_text": "Display name, or empty when Apple never supplied one."},
            "onboarding_completed": {
                "help_text": (
                    "Server-derived, set when the user's first target version is "
                    "created. Never writable. **Do not route on this field alone**: "
                    "a user who left onboarding without setting targets has "
                    "`onboarding_skipped_at` instead, and routing them back to "
                    "onboarding on every launch turns a supported exit into a nag. "
                    "Route to Today when either field is set."
                )
            },
            "onboarding_skipped_at": {
                "help_text": (
                    "When the user chose to leave onboarding without setting "
                    "targets, or null if they never did. Client-written through "
                    "`PATCH /api/users/me/`, because a skip is a choice the server "
                    "cannot derive. Read it together with `onboarding_completed`."
                )
            },
        }


class UserSettingsSerializer(serializers.ModelSerializer):
    """What a client may write to its own user.

    Deliberately not `UserSerializer` with a couple of fields marked read-only.
    Sharing one serializer between the read and the write shape is how
    `onboarding_completed` becomes client-settable: it only takes someone
    relaxing a `read_only_fields` entry to ship the hole, and nothing about the
    read shape would look wrong in review.

    Bounds live on the model fields, so `PATCH` and the admin reject the same
    values. ModelSerializer copies model validators onto the serializer fields.
    """

    class Meta:
        model = User
        fields = [
            "timezone",
            "onboarding_skipped_at",
            "sex",
            "current_weight_lb",
            "goal_weight_lb",
            "goal_timeline_weeks",
            "training_days_per_week",
            "dietary_constraints",
        ]
        extra_kwargs = {
            # `timezone` has a model default, which would otherwise make it
            # required=False but non-nullable with no way to state "unchanged".
            # Partial update covers that; there is simply nothing to clear.
            "timezone": {
                "help_text": (
                    "IANA timezone name, e.g. `America/New_York`. The client "
                    "refreshes this on launch (doc 02), so a user who flies "
                    "somewhere gets their days bucketed locally. Never a numeric "
                    "offset — offsets break across DST."
                )
            },
            # The one client-writable onboarding field, and the asymmetry with
            # `onboarding_completed` is deliberate. That one is a fact about the
            # data, so a client asserting it is a client lying. This one is a
            # choice only the client knows about. The worst a malicious client
            # gets from it is skipping a screen that has a skip button on it.
            "onboarding_skipped_at": {
                "help_text": (
                    "Set this when the user leaves onboarding without targets. Send "
                    "the current time in ISO 8601, within a day of now. Null clears "
                    "it. Setting it stops the launch gate sending them back to "
                    "onboarding on every cold start."
                )
            },
            # **`sex` clears with `""`, not with `null`**, and that is the one
            # inconsistency on this serializer. Review asked for `allow_null`
            # with a coercion, matching the numeric fields beside it.
            #
            # It does not survive the toolchain. `allow_null` on a blank-capable
            # ChoiceField makes drf-spectacular emit `nullable: true` *and* a
            # `NullEnum` member of the same `oneOf`, and orval cannot name that
            # shape: `Duplicate schema names detected: 2x
            # PatchedUserSettingsRequestSex`. The generated client stops building
            # entirely, which is a worse failure than the one it fixes.
            #
            # So the difference is documented instead of absorbed. The help text
            # says it, which means it reaches the OpenAPI schema and the
            # generated client rather than living only here.
            "sex": {
                "help_text": (
                    "Biological sex, `female` or `male`. Asked during onboarding and "
                    "stored because editing targets later needs it. Biological rather "
                    "than gender: it feeds a formula fitted to body composition.\n\n"
                    "**Clear it with an empty string, not with `null`.** Every "
                    "other clearable field here takes `null`; this one is a "
                    'blank-string column and takes `""`. A form that clears '
                    "itself by sending `null` everywhere gets a 400 on this "
                    "field alone."
                ),
            },
            "current_weight_lb": {
                "help_text": (
                    "Current body weight in pounds, 85–500. Asked during onboarding "
                    "and kept, because a target set in Settings weeks later has to be "
                    "bounded against something. The 85 floor is not a sanity check: "
                    "below it the suggested calorie range inverts. Null means not "
                    "answered."
                )
            },
            "goal_weight_lb": {
                "help_text": (
                    "Target body weight in pounds, 85–500, the same band as the current "
                    "weight because they measure the same thing. Null clears it back "
                    "to unanswered."
                )
            },
            "goal_timeline_weeks": {
                "help_text": (
                    "Weeks the user wants to reach the goal weight in, 1–104. A "
                    "duration rather than a date, so it does not go stale. Null "
                    "clears."
                )
            },
            "training_days_per_week": {
                "help_text": "Training days in a typical week, 0–7. Null clears."
            },
            "dietary_constraints": {
                # The column is not nullable, so ModelSerializer would reject
                # null outright and validate_dietary_constraints below would
                # never run. This is what lets "clear it" look the same on every
                # field in this serializer.
                "allow_null": True,
                "help_text": (
                    "Free text, up to 500 characters — 'no dairy, allergic to "
                    "shellfish'. Read by the advice feature (doc 08), not by "
                    "target generation. Send an empty string to clear; null is "
                    "accepted and stored as empty."
                ),
            },
        }

    def validate_onboarding_skipped_at(self, value: datetime | None) -> datetime | None:
        """Refuse a timestamp far from the server's clock.

        The client sends this rather than the server stamping it, which is the
        choice worth explaining. The alternative was accepting any value and
        overwriting it with `timezone.now()`, and that makes a writable field
        quietly ignore what it was sent. A reader of the schema would have no way
        to know.

        So the client's clock is trusted, and checked. Same pattern and same
        window as `effective_from` on a target version, one ticket old.

        Null passes untouched. Clearing the field is how a client says "they came
        back and went through the flow after all".
        """
        if value is None:
            return None

        if abs(value - timezone.now()) > MAX_CLIENT_CLOCK_SKEW:
            raise serializers.ValidationError(
                "Must be within a day of the current time. Send the time of the "
                "skip, not a historical or future date.",
                code="clock_skew",
            )
        return value

    def validate_dietary_constraints(self, value: str | None) -> str:
        """Accept null and store empty.

        The column is `blank=True, default=""` rather than nullable, so there is
        exactly one empty value in the database. Clients still say "clear this"
        with null, the same way they clear the numeric fields, and this is the
        one place that difference is absorbed.
        """
        return value or ""


class SessionSerializer(serializers.Serializer):
    """A created session: who you are, and the tokens to keep being them."""

    user = UserSerializer()
    access = serializers.CharField(
        help_text=(
            "Short-lived bearer token for API calls. Send as `Authorization: Bearer <access>`."
        ),
    )
    refresh = serializers.CharField(
        help_text=(
            "Long-lived token used to mint a new pair. Rotated on every use and "
            "the old one blacklisted, so store it in the Keychain via "
            "expo-secure-store and never in AsyncStorage."
        ),
    )
    created = serializers.BooleanField(
        help_text=(
            "True when this sign-in created the account. The client uses it to "
            "distinguish a first run from a returning user."
        ),
    )


# Schema only, and the one serializer in this module that never runs.
# `SessionRefreshView` does not set `serializer_class`, so simplejwt's
# `TokenRefreshSerializer` still validates the token, rotates it, and
# blacklists the old one. This class exists because that one carries no help
# text for any of it, and the emitted contract is what the mobile client is
# generated from.
#
# So the two can disagree and nothing fails loudly. Flipping
# `ROTATE_REFRESH_TOKENS` off would stop simplejwt returning a `refresh` key
# while this still promised one. Two tests pin that pairing:
# `test_rotation_settings_are_on` in test_tokens.py, and
# `test_refresh_rotates_the_refresh_token` in test_session_lifecycle.py.
#
# Kept out of the docstring on purpose. drf-spectacular copies a serializer's
# docstring into the OpenAPI component, and Orval copies that into the mobile
# client's type -- so anything written there is documentation aimed at a client
# author who cannot see this file and should not have to care which library
# validates the token.
class SessionRefreshSerializer(serializers.Serializer):
    """A refresh token in, a new token pair out.

    One serializer for both directions, because the shapes match. `access` is
    response-only, so the request component drops it.
    """

    refresh = serializers.CharField(
        trim_whitespace=False,
        help_text=(
            "The refresh token from the last sign-in or refresh. It is the "
            "credential for this call: no `Authorization` header is read, "
            "because the whole point of refreshing is that the access token has "
            "expired.\n\n"
            "The response contains a **different** refresh token. Store it, and "
            "discard the one you sent -- rotation blacklists it immediately."
        ),
    )
    access = serializers.CharField(
        read_only=True,
        help_text="A new short-lived access token.",
    )


class SessionDeleteSerializer(serializers.Serializer):
    """What sign-out presents.

    The refresh token, in the body of a DELETE. Unusual, and correct: an access
    token cannot be revoked -- there is no blacklist on the access path -- so
    the refresh token is the only thing there is to destroy.
    """

    refresh = serializers.CharField(
        trim_whitespace=False,
        help_text=(
            "The refresh token to blacklist. Must belong to the authenticated "
            "user; another user's token is rejected."
        ),
    )
