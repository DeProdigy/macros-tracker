"""Serializers for the accounts app.

Fields are declared explicitly (never `fields = "__all__"`) so the emitted
OpenAPI schema is precise enough to generate useful client types from. An
`__all__` on the user model would also publish `password`, `is_superuser`, and
every permission relation into the mobile app's types.
"""

from rest_framework import serializers


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


class SessionUserSerializer(serializers.Serializer):
    """The signed-in user, as the client needs them.

    A deliberate subset. The mobile app routes on `onboarding_completed` and
    displays the rest; nothing else on the model is its business.
    """

    id = serializers.IntegerField(help_text="Stable user identifier.")
    email = serializers.EmailField(
        allow_null=True,
        help_text=(
            "May be null: Apple does not guarantee an email, and may supply a "
            "private relay address rather than a real one."
        ),
    )
    name = serializers.CharField(
        allow_blank=True,
        help_text="Display name, or empty when Apple never supplied one.",
    )
    onboarding_completed = serializers.BooleanField(
        help_text="Whether the client should route to onboarding or to Today.",
    )
    timezone = serializers.CharField(help_text="IANA timezone name, e.g. `America/New_York`.")


class SessionSerializer(serializers.Serializer):
    """A created session: who you are, and the tokens to keep being them."""

    user = SessionUserSerializer()
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
