"""Serializers for the accounts app.

Fields are declared explicitly (never `fields = "__all__"`) so the emitted
OpenAPI schema is precise enough to generate useful client types from. An
`__all__` on the user model would also publish `password`, `is_superuser`, and
every permission relation into the mobile app's types.
"""

from rest_framework import serializers

from accounts.models import User


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
                "help_text": "Whether the client should route to onboarding or to Today."
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
            "sex": {
                "help_text": (
                    "Biological sex, `female` or `male`. Asked during onboarding and "
                    "stored because editing targets later needs it. Biological rather "
                    "than gender: it feeds a formula fitted to body composition. Empty "
                    "string means not answered."
                )
            },
            "current_weight_lb": {
                "help_text": (
                    "Current body weight in pounds, 85–1000. Asked during onboarding "
                    "and kept, because a target set in Settings weeks later has to be "
                    "bounded against something. The 85 floor is not a sanity check: "
                    "below it the suggested calorie range inverts. Null means not "
                    "answered."
                )
            },
            "goal_weight_lb": {
                "help_text": (
                    "Target body weight in pounds, 44–880. Null clears it back to unanswered."
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
