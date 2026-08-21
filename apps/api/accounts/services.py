"""Sign in with Apple — identity token verification.

The whole security argument of E2 sits in this module. A native client hands us
a JWT it received from Apple and asks to be signed in as whoever that token
names. The token arrived over the network from an untrusted device, so until its
signature is checked it is a string of claims an attacker typed, not an identity.
Doc 04 states it flatly: a client-supplied token accepted without verification is
not authentication.

Nothing here is symmetric. Apple signs with a private key we never see and
publishes the matching public keys at a well-known URL, so there is no shared
secret between us and Apple to leak, rotate, or misconfigure. The cost of that
is the JWKS machinery below: because Apple rotates keys on its own schedule, the
token has to name which key signed it (`kid`) and we have to be able to go and
fetch a key we have never seen before.

Four things are checked, and each one closes a specific hole:

    signature   the claims are Apple's, not the caller's
    iss         the token came from appleid.apple.com and not a lookalike
    aud         the token was minted for *this* app -- without this check, a
                valid Apple token issued to any other app in the world
                authenticates against this API
    exp         a token captured last month is not still good
    nonce       a token observed once cannot be replayed into a fresh sign-in

Claims are never read before the signature over them is verified. The one
exception is the `kid` in the unverified header, which is safe only because it
selects from a set of keys we fetched ourselves and can never introduce one.

Failures raise ValidationError with a distinct `code` so tests can prove each
check is doing something. Callers MUST NOT surface those codes: a response that
distinguishes "wrong audience" from "bad signature" is a free oracle for anyone
probing the endpoint. MAC-27 collapses all of them into one generic 401.
"""

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
import jwt.exceptions
from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from jwt.algorithms import RSAAlgorithm
from rest_framework.exceptions import APIException, ValidationError

from accounts.models import Identity, User

# Apple's OpenID configuration, confirmed against
# https://appleid.apple.com/.well-known/openid-configuration.
#
# The issuer has no trailing slash; comparing against one that does fails every
# token and reads like a signature problem.
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"

# Apple's discovery document advertises RS256 and nothing else, so pinning the
# list costs no compatibility. Passing it is not optional: PyJWT will otherwise
# honour whatever the token's own header asks for, which is how the classic JWT
# holes work. A token claiming `alg: none` verifies with no signature at all, and
# one re-signed HS256 verifies if the attacker uses the *public* key as the
# shared secret -- a key we publish the location of, by design.
APPLE_SIGNING_ALGORITHMS = ["RS256"]

# Every claim that must be present. PyJWT treats an absent claim as nothing to
# check rather than as a failure, so without this a token carrying no `aud` at
# all sails past the audience check.
REQUIRED_CLAIMS = ["iss", "aud", "exp", "sub"]

# Small tolerance for clock drift between Railway and Apple. Zero leeway means a
# one-second skew rejects a legitimate sign-in; thirty seconds is far inside the
# lifetime of an Apple identity token, so it widens nothing that matters.
CLOCK_SKEW_LEEWAY_SECONDS = 30

JWKS_CACHE_KEY = "apple:jwks"
JWKS_CACHE_SECONDS = 60 * 60 * 24

# Apple's JWKS fetch times out rather than holding a worker open on a hung
# connection. This runs on the sign-in path.
JWKS_FETCH_TIMEOUT_SECONDS = 5

# Cooldown on the unknown-`kid` refetch. Apple rotates keys, so a `kid` we have
# never seen is routine and refusing to refetch would break every sign-in on
# rotation day. But a refetch is by definition a cache bypass, so an attacker
# sending a thousand tokens carrying `kid: "bogus"` would otherwise make us send
# a thousand requests to Apple -- our own endpoint turned into an amplifier.
# One refetch per window, whatever the traffic. A genuine rotation is delayed by
# at most this long, well inside the overlap Apple leaves when publishing a key.
JWKS_REFRESH_LOCK_KEY = "apple:jwks:refresh-lock"
JWKS_REFRESH_COOLDOWN_SECONDS = 300


@dataclass(frozen=True)
class AppleClaims:
    """What a verified token told us.

    Named for what it holds rather than what it becomes. `Identity` is the row
    we store; this is the assertion Apple signed. Calling both "identity" was
    the shape of a naming bug, so the dataclass took the other name.

    Deliberately not the raw claim dict. A dict invites the caller to reach for
    `email_verified`, which Apple documents as always true and which therefore
    carries no information, or for `transfer_sub`, which means something quite
    different from `sub` and would silently work most of the time.

    `subject` is Apple's `sub` claim and is the account join key. Never the
    email: a user may elect a Hide My Email relay address, and relay addresses
    can change.

    `email` is None when the claim is absent, which happens for real users --
    a stale app association or a Managed Apple ID. The caller writes it only
    when present and never overwrites a stored address with None (doc 04).

    `is_private_email` is None when Apple did not say, which is not the same as
    False. `real_user_status` is None on every authorization after the first,
    because Apple only sends it once.
    """

    subject: str
    email: str | None
    is_private_email: bool | None
    real_user_status: int | None


def _optional_bool(value: Any) -> bool | None:
    """Read a claim Apple has sent as both a bool and a string.

    `is_private_email` arrives as a real JSON boolean in the identity token, but
    Apple's own flows have historically emitted `"true"` / `"false"` strings and
    the docs do not promise which. Anything unrecognised becomes None rather
    than False, because "Apple did not tell us" and "Apple said no" are
    different answers and only one of them is safe to act on.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return None


def _optional_real_user_status(value: Any) -> int | None:
    """Read Apple's bot signal, rejecting anything outside the documented set.

    An unrecognised number is dropped rather than stored. A value we cannot
    interpret is worse than no value: it survives into the database looking
    like a fact, and the next reader has no way to tell it apart from one.

    `isinstance(value, bool)` is excluded first because in Python `True` is an
    int, and `True` would otherwise store as status 1 ("Unknown").
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value in Identity.RealUserStatus.values:
        return value
    return None


def _reject(code: str, message: str) -> ValidationError:
    """Build a rejection carrying a machine-readable code.

    Returned rather than raised so call sites read `raise _reject(...)`, which
    keeps the control flow visible at the point it happens.
    """
    return ValidationError({"identity_token": [message]}, code=code)


def _fetch_jwks() -> dict[str, Any]:
    """Fetch Apple's public signing keys.

    stdlib rather than requests or httpx, neither of which this project depends
    on. This is one call per day per worker, so connection pooling buys nothing,
    and a stdlib function is trivial for the tests to replace.

    This is the module's only network call, and it is the seam the test suite
    monkeypatches -- which is what lets the tests verify real RS256 signatures
    while never touching the network.
    """
    try:
        with urllib.request.urlopen(  # noqa: S310 - constant https URL
            APPLE_JWKS_URL, timeout=JWKS_FETCH_TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise _reject("jwks_unavailable", "Could not reach Apple to verify the token.") from exc

    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list):
        raise _reject("jwks_unavailable", "Could not reach Apple to verify the token.")

    return {"keys": keys}


def _load_jwks(*, refresh: bool = False) -> dict[str, Any]:
    """Return Apple's JWKS, from cache unless a refresh is demanded."""
    if not refresh:
        cached = cache.get(JWKS_CACHE_KEY)
        if cached is not None:
            return cached

    jwks = _fetch_jwks()
    cache.set(JWKS_CACHE_KEY, jwks, JWKS_CACHE_SECONDS)
    return jwks


def _find_key(jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
    for key in jwks["keys"]:
        if isinstance(key, dict) and key.get("kid") == kid:
            return key
    return None


def _signing_jwk(kid: str) -> dict[str, Any]:
    """Resolve a `kid` to Apple's matching public key.

    The miss path is the interesting one. An unknown `kid` usually means Apple
    published a new key since we last looked, so we go again -- but exactly once,
    and only if nobody else went recently. See JWKS_REFRESH_LOCK_KEY above for
    why the cooldown exists.
    """
    jwk = _find_key(_load_jwks(), kid)
    if jwk is not None:
        return jwk

    # cache.add() writes only when the key is absent and reports whether it did,
    # which makes it a lock with an expiry built in and no cleanup path.
    if not cache.add(JWKS_REFRESH_LOCK_KEY, True, JWKS_REFRESH_COOLDOWN_SECONDS):
        raise _reject("unknown_key", "Token was signed with an unrecognised key.")

    jwk = _find_key(_load_jwks(refresh=True), kid)
    if jwk is None:
        raise _reject("unknown_key", "Token was signed with an unrecognised key.")

    return jwk


def _unverified_kid(token: str) -> str:
    """Read the `kid` from the token header without verifying anything.

    Untrusted input, and treated as such: its only power is to pick one key out
    of the set we fetched from Apple. It cannot supply a key, and a `kid` that
    matches nothing is rejected rather than defaulted.
    """
    if not isinstance(token, str) or not token:
        raise _reject("malformed_token", "Not a valid identity token.")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise _reject("malformed_token", "Not a valid identity token.") from exc

    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _reject("malformed_token", "Token header names no signing key.")

    return kid


def _verify_nonce(claims: dict[str, Any], expected_nonce: str) -> None:
    """Compare the token's nonce against the value the client committed to.

    How the nonce round-trips, settled in the MAC-26 plan against Apple's
    behaviour rather than against the ticket, which had it backwards:

    Apple does not hash anything. In the native flow the *client* computes
    SHA256 of its raw nonce and sets that digest on
    ASAuthorizationAppleIDRequest.nonce; Apple copies the string into the claim
    verbatim. (The web flow echoes a raw nonce, which is where the confusion
    comes from.) So the client sends us the raw value and we hash it here.

    Digest encoding is lowercase hex, because expo-crypto's digestStringAsync
    returns hex by default and both ends of this are ours. An encoding mismatch
    fails identically to a wrong nonce, which is a miserable thing to debug.

    compare_digest rather than `==` to keep the comparison constant-time. The
    practical risk of leaking a nonce byte-by-byte over the network is slight,
    but this is the standard tool for comparing a secret and using it costs
    nothing.
    """
    claimed = claims.get("nonce")
    if not isinstance(claimed, str):
        raise _reject("nonce_mismatch", "Token does not carry the expected nonce.")

    digest = hashlib.sha256(expected_nonce.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(claimed, digest):
        raise _reject("nonce_mismatch", "Token does not carry the expected nonce.")


def verify_apple_identity_token(token: str, *, expected_nonce: str) -> AppleClaims:
    """Verify an Apple identity token and return who it names.

    `expected_nonce` is the raw value the client generated for this sign-in, and
    it is keyword-only with no default on purpose. An optional nonce is a replay
    check that quietly stops running the first time a caller forgets it.

    Raises ValidationError on every failure. See the module docstring: the codes
    are for tests, not for clients.
    """
    client_id = settings.APPLE_CLIENT_ID
    if not client_id:
        # Deliberately raised here rather than at import. A Railway deploy with
        # this unset still boots and still answers /api/health/; it fails on the
        # first sign-in instead. The alternative -- defaulting to "" and letting
        # the `aud` check compare against it -- is how the most important check
        # in this module would silently do nothing.
        raise ImproperlyConfigured("APPLE_CLIENT_ID must be set to verify Apple identity tokens.")

    kid = _unverified_kid(token)

    try:
        public_key = RSAAlgorithm.from_jwk(_signing_jwk(kid))
    except (jwt.InvalidKeyError, ValueError, TypeError, KeyError) as exc:
        # A matching `kid` is not the same as a usable RSA key. _find_key only
        # matches on `kid`, so any JWKS entry that is not a well-formed RSA
        # public key lands here -- most plausibly the day Apple publishes an EC
        # key, which raises "Not an RSA key".
        #
        # This needs its own clause because InvalidKeyError does *not* subclass
        # InvalidTokenError, so none of the handlers below would catch it, and
        # it is raised outside their try block regardless. Left alone it escapes
        # as a 500 and breaks this module's one promise: every failure is a
        # ValidationError.
        #
        # Its own code rather than folding into `unknown_key`, so an Apple
        # algorithm migration reads as exactly that in the logs instead of
        # hiding among ordinary unrecognised-kid noise.
        raise _reject("unusable_key", "Token was signed with an unsupported key.") from exc

    try:
        claims = jwt.decode(
            token,
            key=public_key,  # type: ignore[arg-type]
            algorithms=APPLE_SIGNING_ALGORITHMS,
            audience=client_id,
            issuer=APPLE_ISSUER,
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _reject("token_expired", "Identity token has expired.") from exc
    except jwt.InvalidAudienceError as exc:
        raise _reject("invalid_audience", "Identity token was issued for another app.") from exc
    except jwt.InvalidIssuerError as exc:
        raise _reject("invalid_issuer", "Identity token was not issued by Apple.") from exc
    except jwt.MissingRequiredClaimError as exc:
        raise _reject("missing_claim", "Identity token is missing a required claim.") from exc
    # PyJWT type-checks `sub` on its own and raises this. Mapped explicitly
    # rather than left to the backstop below, so an unusable subject reports the
    # same code as an absent one instead of the vague `invalid_token`.
    except jwt.exceptions.InvalidSubjectError as exc:
        raise _reject("missing_claim", "Identity token is missing a required claim.") from exc
    # InvalidSignatureError subclasses DecodeError, and InvalidAlgorithmError is
    # the rejection for `alg: none` and for HS256 confusion. All three are the
    # signature layer refusing the token, so they share a code -- and this clause
    # must precede the DecodeError one below or it would never be reached.
    except (jwt.InvalidSignatureError, jwt.InvalidAlgorithmError) as exc:
        raise _reject("invalid_signature", "Identity token signature is invalid.") from exc
    except jwt.DecodeError as exc:
        raise _reject("malformed_token", "Not a valid identity token.") from exc
    except jwt.InvalidTokenError as exc:
        # Backstop for anything PyJWT adds later. Rejecting an unrecognised
        # failure is the only safe default; falling through would accept it.
        raise _reject("invalid_token", "Identity token failed verification.") from exc

    _verify_nonce(claims, expected_nonce)

    # PyJWT covers `sub` being absent (MissingRequiredClaimError) and being a
    # non-string (InvalidSubjectError), both handled above. It accepts the empty
    # string, which is the one gap: AppleClaims declares `subject: str` and
    # MAC-27 uses it as the account join key, so an empty subject would become a
    # database lookup for "" and match the wrong thing or nothing at all.
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject:
        raise _reject("missing_claim", "Identity token is missing a required claim.")

    email = claims.get("email")
    return AppleClaims(
        subject=subject,
        email=email if isinstance(email, str) and email else None,
        is_private_email=_optional_bool(claims.get("is_private_email")),
        real_user_status=_optional_real_user_status(claims.get("real_user_status")),
    )


def record_authentication(identity: Identity, *, claims: AppleClaims) -> None:
    """Stamp a successful sign-in on both the person and the credential.

    Fixes three things that were quietly broken.

    `User.last_login` was never written. simplejwt has an `UPDATE_LAST_LOGIN`
    setting, but it only fires inside `TokenObtainPairSerializer`, and we mint
    tokens directly with `RefreshToken.for_user()` -- so turning it on would
    have changed nothing. Meanwhile `accounts/admin.py` displays the field, so
    every active user read as "never logged in".

    The general lesson is worth more than the fix: `last_login` arrived free
    from `AbstractBaseUser`. Nobody declared it, so nobody reviewed it, and it
    sat holding a constant -- exactly what MAC-25 deleted `is_email_verified`
    for. Inherited fields dodge the scrutiny declared ones get.

    `update_last_login` is Django's own receiver rather than a hand-written
    save. It uses `update_fields`, so it writes one column instead of the whole
    row, which matters here because a concurrent request holding a stale user
    object would otherwise clobber whatever it had cached.

    Refreshing `is_private_email` but not `real_user_status` is deliberate and
    is the whole reason this takes claims rather than just an identity. A user
    can switch between a relay address and their real one, so the first is
    current state. Apple sends the second only on the first authorization, so a
    later token carries None -- and writing that would erase a real signal.
    """
    now = timezone.now()
    fields = ["last_authenticated_at"]
    identity.last_authenticated_at = now

    if claims.is_private_email is not None:
        identity.is_private_email = claims.is_private_email
        fields.append("is_private_email")

    identity.save(update_fields=fields)

    # update_last_login is a signal receiver, so its first argument is the
    # sender and it goes unused. Passing the model class rather than None
    # because that is what the signature actually asks for -- None works at
    # runtime and is the common idiom, but it fails type checking, and silencing
    # that with an ignore would hide a real signature change later.
    update_last_login(type(identity.user), identity.user)


class InvalidAppleCredential(APIException):
    """A sign-in attempt that failed verification.

    Deliberately not `AuthenticationFailed`, which would be the obvious choice.
    DRF rewrites `AuthenticationFailed` and `NotAuthenticated` to 403 when the
    view has no authenticator to build a `WWW-Authenticate` header from -- and
    this endpoint must set `authentication_classes = []`, because it is the
    request that creates the session in the first place. Measured, not assumed:

        authentication_classes = []  -> 403
        default auth classes         -> 401

    A plain `APIException` subclass is untouched by that rewrite, so it keeps
    the 401 a failed credential deserves. The alternative, overriding
    `get_authenticate_header`, means advertising a bearer challenge the endpoint
    does not actually issue: a misleading header to fix a status code.

    One message for every cause, on purpose. `verify_apple_identity_token`
    raises distinct codes so its tests can prove each check runs, and a response
    that told the caller "wrong audience" rather than "bad signature" would hand
    an attacker a free oracle for probing.
    """

    status_code = 401
    default_detail = "Could not verify the Apple credential."
    default_code = "invalid_apple_credential"


@dataclass(frozen=True)
class ResolvedSession:
    """The outcome of resolving one sign-in.

    `created` and `reactivated` are reported rather than inferred, because the
    caller cannot tell them apart afterwards: a restored user and a returning
    one look identical once the row is saved. They are separate flags rather
    than one enum because a brand-new user is never reactivated, so no third
    state exists to name.
    """

    user: User
    identity: Identity
    created: bool
    reactivated: bool


def resolve_apple_user(claims: AppleClaims, *, name: str = "") -> ResolvedSession:
    """Find or create the user behind a set of verified claims.

    The lookup is `(provider, subject)` and never the email. A user may elect
    Apple's private relay, relay addresses can change, and Apple sends the email
    claim inconsistently. Any one of those breaks an email-keyed lookup, and the
    failure is that two sign-ins by one person produce two accounts.

    **Reactivation has no time limit.** If the row is here and the same Apple
    credential presents itself, it is the same person, so they get their account
    back. The 30-day figure belongs to MAC-29's purge as a retention policy, and
    the purge enforces it by deleting the row -- after which this function takes
    the create branch and gives them a clean account. Putting a second copy of
    that deadline here would mean a date comparison on the sign-in path whose
    only reachable outcome, in a working system, is "the purge is broken".

    `name` is separate from `claims` because it is not a claim. Apple sends no
    name in the token; the client forwards what it got from the credential on
    first authorization. Keeping it out of `AppleClaims` keeps the boundary
    visible: everything in that dataclass is signed, and this is not.
    """
    with transaction.atomic():
        identity = (
            Identity.objects.select_related("user")
            .filter(provider=Identity.Provider.APPLE, subject=claims.subject)
            .first()
        )

        if identity is None:
            user = User.objects.create_apple_user(
                apple_user_id=claims.subject,
                email=claims.email,
                is_private_email=claims.is_private_email,
                real_user_status=claims.real_user_status,
                name=name,
            )
            return ResolvedSession(
                user=user,
                identity=user.identities.get(),
                created=True,
                reactivated=False,
            )

        user = identity.user
        updates: list[str] = []

        # Absence is not a change. Apple omits the email claim for real users --
        # a stale app association, a Managed Apple ID -- and never resends the
        # name after the first authorization. Writing those absences through
        # would erase a working address on someone's second login, which is a
        # bug that cannot appear until a real user comes back.
        if claims.email:
            normalized = User.objects.normalize_email(claims.email)
            if normalized != user.email:
                user.email = normalized
                updates.append("email")

        if name and name != user.name:
            user.name = name
            updates.append("name")

        reactivated = user.deleted_at is not None
        if reactivated:
            user.deleted_at = None
            user.is_active = True
            updates.extend(["deleted_at", "is_active"])

        if updates:
            user.save(update_fields=updates)

        return ResolvedSession(
            user=user,
            identity=identity,
            created=False,
            reactivated=reactivated,
        )


def delete_account(user: User) -> bool:
    """Soft-delete a user and revoke every refresh token they hold.

    Returns True if this call performed the deletion, False if the account was
    already deleted. The caller answers 204 either way -- the flag exists for
    logs and tests, not for the response.

    Three writes, and each one closes a different hole:

    `deleted_at` records the deletion for the purge that a later ticket adds.
    On its own it stops nothing: no authentication path reads this column.

    `is_active=False` is what actually locks the account. simplejwt's
    `JWTAuthentication` checks it on every request, so the access token the
    client is still holding stops working on the next call rather than whenever
    it expires -- up to 15 minutes of authenticated requests, otherwise.

    Blacklisting the outstanding refresh tokens stops the other half. A refresh
    is a token exchange, and doc 04 asks for all tokens revoked; without this a
    stored refresh token still mints new access tokens, which then fail the
    `is_active` check. Belt and braces on purpose: the two guards fail
    independently.

    Identities are deliberately left alone. Soft delete is a property of the
    person, and `resolve_apple_user` restores the account by finding the
    Identity row for the same Apple `sub`. Deleting it here would turn every
    return visit into a brand-new account.

    **Deleting twice does not move `deleted_at`.** A retried request must not
    push the retention deadline forward, and a client that retries a 204 it
    never saw is ordinary. The early return is what makes the endpoint
    idempotent rather than merely repeatable.
    """
    # Imported here rather than at module scope. The blacklist models live in an
    # app that is only installed because BLACKLIST_AFTER_ROTATION needs
    # somewhere to write, and a top-level import would make this module fail to
    # load if that app were ever removed from INSTALLED_APPS.
    from rest_framework_simplejwt.token_blacklist.models import (
        BlacklistedToken,
        OutstandingToken,
    )

    with transaction.atomic():
        if user.deleted_at is not None:
            return False

        user.deleted_at = timezone.now()
        user.is_active = False
        user.save(update_fields=["deleted_at", "is_active"])

        # get_or_create, not create: a token blacklisted by an earlier sign-out
        # is still an outstanding row, and `create` would raise on its unique
        # constraint and roll the whole deletion back.
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

    return True
