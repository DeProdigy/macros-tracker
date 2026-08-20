"""Tests for Apple identity token verification.

The assertions that carry weight are the refusals. A suite proving only that a
good token verifies proves the function can parse a JWT, which was never in
doubt. Each bad input below asserts a *distinct* error code, because a suite
where everything raises the same generic error cannot tell you whether the
`aud` check runs at all -- and `aud` is the check that stops another app's Apple
tokens from signing in here.

Nothing talks to Apple. A real 2048-bit RSA keypair is generated once per
session, tokens are signed with it, and `_fetch_jwks` is replaced with a stub
returning the matching public key. So the signature verification exercised here
is the real thing over fake credentials -- the same trick
uploads/tests/test_presign.py uses to sign real URLs against a fake R2.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from jwt.algorithms import RSAAlgorithm
from rest_framework.exceptions import ValidationError

from accounts import services

CLIENT_ID = "app.macros-tracker.test"
OTHER_CLIENT_ID = "com.someone-else.app"
APPLE_KID = "test-apple-key"
RAW_NONCE = "raw-nonce-the-client-generated"
HASHED_NONCE = hashlib.sha256(RAW_NONCE.encode()).hexdigest()


def _keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def apple_key() -> rsa.RSAPrivateKey:
    """The key standing in for Apple's. Session-scoped: RSA keygen is slow
    enough that doing it per test is noticeable."""
    return _keypair()


@pytest.fixture(scope="session")
def impostor_key() -> rsa.RSAPrivateKey:
    """A valid key that Apple never published. Used to prove the signature is
    checked rather than merely parsed."""
    return _keypair()


def _jwks_for(key: rsa.RSAPrivateKey, kid: str = APPLE_KID) -> dict[str, Any]:
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


class FetchStub:
    """Stands in for the one network call, and counts itself.

    The count is the point for two of the tests below: an unknown `kid` must
    refetch exactly once, and must not refetch again while the cooldown holds.
    """

    def __init__(self, jwks: dict[str, Any]) -> None:
        self.jwks = jwks
        self.calls = 0

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        return self.jwks


@pytest.fixture(autouse=True)
def apple_settings(settings):
    settings.APPLE_CLIENT_ID = CLIENT_ID
    return settings


@pytest.fixture(autouse=True)
def clear_cache():
    """LocMemCache outlives a test. Without this the JWKS and the refetch
    cooldown lock leak between tests and the call-count assertions become
    order-dependent."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fetch(monkeypatch, apple_key) -> FetchStub:
    stub = FetchStub(_jwks_for(apple_key))
    monkeypatch.setattr(services, "_fetch_jwks", stub)
    return stub


def make_token(
    apple_key: rsa.RSAPrivateKey,
    *,
    signing_key: rsa.RSAPrivateKey | None = None,
    kid: str = APPLE_KID,
    audience: str | None = CLIENT_ID,
    issuer: str | None = services.APPLE_ISSUER,
    expires_in: int = 600,
    nonce: str | None = HASHED_NONCE,
    subject: Any = "000123.abcdef.4567",
    email: str | None = "user@example.com",
    drop: tuple[str, ...] = (),
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": now,
        "exp": now + expires_in,
    }
    if nonce is not None:
        claims["nonce"] = nonce
    if email is not None:
        claims["email"] = email
    for claim in drop:
        claims.pop(claim, None)

    return jwt.encode(
        claims,
        signing_key or apple_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


def verify(token: str, nonce: str = RAW_NONCE) -> services.AppleIdentity:
    return services.verify_apple_identity_token(token, expected_nonce=nonce)


def code_of(exc_info) -> str:
    """DRF wraps the detail in a dict of lists of ErrorDetail; the code rides on
    the ErrorDetail string itself."""
    return exc_info.value.detail["identity_token"][0].code


# --- the happy path ---------------------------------------------------------


def test_valid_token_returns_the_identity(apple_key, fetch):
    identity = verify(make_token(apple_key))

    assert identity.subject == "000123.abcdef.4567"
    assert identity.email == "user@example.com"
    assert fetch.calls == 1


def test_second_verification_uses_the_cached_jwks(apple_key, fetch):
    """Apple is not consulted per sign-in. Without the cache this is a network
    round trip on the critical path of every authentication."""
    verify(make_token(apple_key))
    verify(make_token(apple_key))

    assert fetch.calls == 1


def test_missing_email_claim_is_not_a_failure(apple_key, fetch):
    """Apple does not guarantee an email even in the token (doc 04). A user
    without one must still be able to sign in."""
    identity = verify(make_token(apple_key, email=None))

    assert identity.subject == "000123.abcdef.4567"
    assert identity.email is None


# --- signature ---------------------------------------------------------------


def test_token_signed_by_another_key_is_rejected(apple_key, impostor_key, fetch):
    """Same `kid`, valid JWT, wrong signer. This is the test that proves the
    signature is verified rather than decoded."""
    token = make_token(apple_key, signing_key=impostor_key)

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "invalid_signature"


def test_hs256_algorithm_confusion_is_rejected(apple_key, fetch):
    """The classic JWT attack: re-sign the token HS256 using Apple's *public*
    key as the shared secret. It works against any verifier that trusts the
    token's own `alg` header, and the "secret" is a value we publish the
    location of. Ours pins the algorithm list, so it does not.

    Assembled by hand rather than with jwt.encode(), which refuses to use a PEM
    as an HMAC secret. That refusal is PyJWT protecting the signing side; an
    attacker has no such scruples and simply concatenates the parts.
    """
    public_pem = apple_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def segment(data: dict[str, Any]) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=")

    now = int(time.time())
    header = segment({"alg": "HS256", "typ": "JWT", "kid": APPLE_KID})
    payload = segment(
        {
            "iss": services.APPLE_ISSUER,
            "aud": CLIENT_ID,
            "sub": "000123.attacker.0000",
            "exp": now + 600,
            "nonce": HASHED_NONCE,
        }
    )
    signing_input = header + b"." + payload
    signature = base64.urlsafe_b64encode(
        hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    ).rstrip(b"=")
    forged = (signing_input + b"." + signature).decode()

    with pytest.raises(ValidationError) as exc_info:
        verify(forged)

    assert code_of(exc_info) == "invalid_signature"


# --- claims ------------------------------------------------------------------


def test_token_for_another_app_is_rejected(apple_key, fetch):
    """The single most important assertion here. Apple signs tokens for every
    app; only the `aud` check makes ours ours."""
    token = make_token(apple_key, audience=OTHER_CLIENT_ID)

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "invalid_audience"


def test_token_from_a_lookalike_issuer_is_rejected(apple_key, fetch):
    token = make_token(apple_key, issuer="https://appleid.apple.com.evil.example")

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "invalid_issuer"


def test_expired_token_is_rejected(apple_key, fetch):
    token = make_token(apple_key, expires_in=-3600)

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "token_expired"


@pytest.mark.parametrize("claim", ["aud", "iss", "exp", "sub"])
def test_absent_required_claim_is_rejected(apple_key, fetch, claim):
    """PyJWT treats an absent claim as nothing to check rather than a failure,
    so a token with no `aud` at all would otherwise pass the audience check."""
    token = make_token(apple_key, drop=(claim,))

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "missing_claim"


# --- nonce -------------------------------------------------------------------


def test_wrong_nonce_is_rejected(apple_key, fetch):
    """A token captured off the wire cannot be replayed into a new sign-in,
    because the attacker cannot produce the raw nonce behind the digest."""
    token = make_token(apple_key)

    with pytest.raises(ValidationError) as exc_info:
        verify(token, nonce="some-other-nonce")

    assert code_of(exc_info) == "nonce_mismatch"


def test_absent_nonce_claim_is_rejected(apple_key, fetch):
    """Missing is not the same as matching."""
    token = make_token(apple_key, nonce=None)

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "nonce_mismatch"


def test_raw_nonce_in_the_claim_is_rejected(apple_key, fetch):
    """Guards the contract MAC-30 has to implement. Apple copies the client's
    value verbatim, so a client that forgot to hash produces a raw nonce here
    and must fail rather than silently pass."""
    token = make_token(apple_key, nonce=RAW_NONCE)

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "nonce_mismatch"


# --- key rotation ------------------------------------------------------------


def test_unknown_kid_refetches_exactly_once(apple_key, fetch):
    """Apple rotates keys, so an unfamiliar `kid` is routine and deserves a
    second look. Exactly one, though -- see the cooldown test below."""
    token = make_token(apple_key, kid="a-kid-apple-has-not-published")

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "unknown_key"
    assert fetch.calls == 2


def test_rotated_key_is_picked_up_on_the_refetch(apple_key, fetch):
    """The reason the refetch exists. A cache holding yesterday's keys must not
    break sign-in the day Apple publishes a new one."""
    verify(make_token(apple_key))
    assert fetch.calls == 1

    fetch.jwks = _jwks_for(apple_key, kid="apples-new-key")
    identity = verify(make_token(apple_key, kid="apples-new-key"))

    assert identity.subject == "000123.abcdef.4567"
    assert fetch.calls == 2


def test_repeated_unknown_kids_do_not_amplify(apple_key, fetch):
    """Without the cooldown lock, this endpoint becomes a way to make us flood
    Apple: every junk `kid` bypasses the cache and triggers a fetch."""
    for _ in range(20):
        with pytest.raises(ValidationError):
            verify(make_token(apple_key, kid="junk"))

    assert fetch.calls == 2


# --- malformed input ---------------------------------------------------------


@pytest.mark.parametrize(
    "garbage",
    ["", "not-a-jwt", "only.two", "a.b.c", "...", "Bearer abc.def.ghi"],
)
def test_malformed_input_never_reaches_the_crypto_path(fetch, garbage):
    with pytest.raises(ValidationError) as exc_info:
        verify(garbage)

    assert code_of(exc_info) == "malformed_token"
    assert fetch.calls == 0


def test_token_header_without_a_kid_is_rejected(apple_key, fetch):
    now = int(time.time())
    token = jwt.encode({"sub": "x", "exp": now + 600}, apple_key, algorithm="RS256")

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "malformed_token"


# --- unusable keys -----------------------------------------------------------


def test_matching_kid_that_is_not_an_rsa_key_is_rejected(apple_key, fetch, monkeypatch):
    """A matching `kid` is not the same as a usable key. The realistic version
    of this is the day Apple publishes an EC key: PyJWT's InvalidKeyError does
    not subclass InvalidTokenError and is raised outside the decode block, so
    without its own clause it escapes as a 500."""
    fetch.jwks = {"keys": [{"kty": "EC", "crv": "P-256", "x": "a", "y": "b", "kid": APPLE_KID}]}

    with pytest.raises(ValidationError) as exc_info:
        verify(make_token(apple_key))

    assert code_of(exc_info) == "unusable_key"


def test_matching_kid_with_a_truncated_key_is_rejected(apple_key, fetch):
    """Same clause, different shape: the right `kty` with the key material
    missing."""
    fetch.jwks = {"keys": [{"kty": "RSA", "kid": APPLE_KID, "alg": "RS256"}]}

    with pytest.raises(ValidationError) as exc_info:
        verify(make_token(apple_key))

    assert code_of(exc_info) == "unusable_key"


@pytest.mark.parametrize("subject", [12345, ["a"], {"s": 1}])
def test_non_string_subject_is_rejected(apple_key, fetch, subject):
    """PyJWT type-checks `sub` itself and raises InvalidSubjectError. Mapped to
    the same code as an absent claim rather than the generic backstop."""
    token = make_token(apple_key, subject=subject)

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "missing_claim"


def test_empty_subject_is_rejected(apple_key, fetch):
    """The gap PyJWT leaves. It accepts "" as a valid string subject, which
    would become a database lookup for an empty account key."""
    token = make_token(apple_key, subject="")

    with pytest.raises(ValidationError) as exc_info:
        verify(token)

    assert code_of(exc_info) == "missing_claim"


# --- configuration -----------------------------------------------------------


def test_missing_client_id_raises_rather_than_verifying(apple_key, fetch, settings):
    """An empty APPLE_CLIENT_ID must not fall through to comparing `aud`
    against "". Failing loudly here beats disabling the audience check."""
    settings.APPLE_CLIENT_ID = ""

    with pytest.raises(ImproperlyConfigured):
        verify(make_token(apple_key))


def test_jwks_fetch_failure_is_not_a_silent_pass(monkeypatch, apple_key):
    def boom() -> dict[str, Any]:
        raise services._reject("jwks_unavailable", "Could not reach Apple to verify the token.")

    monkeypatch.setattr(services, "_fetch_jwks", boom)

    with pytest.raises(ValidationError) as exc_info:
        verify(make_token(apple_key))

    assert code_of(exc_info) == "jwks_unavailable"
