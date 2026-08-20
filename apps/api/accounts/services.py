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
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from jwt.algorithms import RSAAlgorithm
from rest_framework.exceptions import ValidationError

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
class AppleIdentity:
    """The only two things we take from a verified token.

    Deliberately not the raw claim dict. A dict invites the caller to reach for
    `email_verified` (Apple documents it as always true, so it carries no
    information) or `real_user_status`, neither of which doc 02 has a column for
    and doc 04 explicitly declined to store.

    `subject` is Apple's `sub` claim and is the account join key. Never the
    email: a user may elect a Hide My Email relay address, and relay addresses
    can change.

    `email` is None when the claim is absent, which happens for real users --
    a stale app association or a Managed Apple ID. The caller writes it only
    when present and never overwrites a stored address with None (doc 04).
    """

    subject: str
    email: str | None


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


def verify_apple_identity_token(token: str, *, expected_nonce: str) -> AppleIdentity:
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
        raise ImproperlyConfigured(
            "APPLE_CLIENT_ID must be set to verify Apple identity tokens."
        )

    kid = _unverified_kid(token)
    public_key = RSAAlgorithm.from_jwk(_signing_jwk(kid))

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

    subject = claims["sub"]
    email = claims.get("email")
    return AppleIdentity(
        subject=subject,
        email=email if isinstance(email, str) and email else None,
    )
