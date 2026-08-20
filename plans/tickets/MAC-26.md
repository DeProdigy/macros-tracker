# MAC-26 — Verify Apple identity tokens against JWKS

Approved 20 Aug 2026. Linear:
[MAC-26](https://linear.app/hintology/issue/MAC-26/verify-apple-identity-tokens-against-jwks).

## Context

The security core of E2. A native client hands the API a JWT it got from Apple
and asks to be signed in as whoever that token names. Until the signature is
checked, that token is a string of claims an attacker typed. Doc 04 states it
flatly: a client-supplied token accepted without verification is not
authentication.

One service function and its tests. No endpoint, no view, no serializer, no
migration. MAC-27 builds the sign-in endpoint on top of this and MAC-30 builds
the mobile half.

## The correction that shaped the plan

The ticket said *"Apple places the SHA256 hash of the client's nonce in the
`nonce` claim."* That is backwards, and the ticket itself asked for it to be
confirmed against Apple rather than trusted.

Apple hashes nothing in the native flow. The **client** computes SHA256 of its
raw nonce, sets that digest on `ASAuthorizationAppleIDRequest.nonce`, and Apple
copies the string into the claim verbatim. Apple's *web* flow does echo a raw
nonce, which is where the confusion comes from and why Supabase and better-auth
both carry issues for it.

The server code is identical either way, which is what makes this worth writing
down rather than shrugging at. The entire difference lands on MAC-30: a client
that sets the raw nonce produces a raw nonce in the claim, and every sign-in
fails looking like a server bug.

| Side | Does |
| -- | -- |
| Mobile (MAC-30) | Generates a random `raw_nonce`. Computes SHA256 as **lowercase hex** via `expo-crypto`'s `digestStringAsync`, whose default encoding is hex. Passes the digest to `signInAsync({ nonce })` |
| Mobile → API (MAC-27) | Posts the **raw** value alongside the token, never the digest |
| Server (this ticket) | Hashes the raw value and compares to the claim with `hmac.compare_digest` |

Hex rather than base64url only because `expo-crypto` defaults to hex and both
ends are ours. It is recorded because an encoding mismatch fails identically to
a wrong nonce, which is a miserable thing to debug.
`test_raw_nonce_in_the_claim_is_rejected` exists to stop MAC-30 getting this
wrong silently.

## Verified against Apple, not against the ticket

Fetched `appleid.apple.com/.well-known/openid-configuration` directly:

- `jwks_uri` is `https://appleid.apple.com/auth/keys`, currently serving three
  RSA keys with distinct `kid`s
- `issuer` is exactly `https://appleid.apple.com`, no trailing slash
- `id_token_signing_alg_values_supported` is `["RS256"]` and nothing else, so
  pinning the algorithm list costs no compatibility
- `claims_supported` includes both `nonce` and `nonce_supported`. The second
  exists because early iOS 13 builds handled the nonce inconsistently; current
  SDKs do not need it

## Approach

### 1. Dependency

`uv add "pyjwt[crypto]"` from `apps/api`. PyJWT 2.13 was already present via
simplejwt, but `cryptography` was not, so RS256 raised at algorithm lookup.
Confirmed in the venv before adding.

### 2. Settings — `config/settings/base.py`

**`APPLE_CLIENT_ID` did not actually exist.** The ticket said the Apple settings
were already there. They were in `.env.example`, but no settings module read any
of them, so `settings.APPLE_CLIENT_ID` would have raised `AttributeError`. Added
with an empty default plus a guard: an empty value raises `ImproperlyConfigured`
rather than letting the audience check compare `aud` against `""`.

The guard fires inside the function, never at import, so a Railway deploy without
it still boots and still answers `/api/health/`. It fails on the first sign-in
instead, which is the right trade while E2 is half-built.

**There was no `CACHES` block either.** Django was silently using per-process
`LocMemCache`. Declared explicitly, which changes no behaviour, so that the
consequence has somewhere to live: with N gunicorn workers there are N copies of
the JWKS and N independent cooldown locks, so the amplification ceiling is N
refetches per window rather than one. Bounded and fine at this size. The comment
marks where this becomes Redis — the first time something cached needs to be
consistent across workers.

### 3. The service — `accounts/services.py`

Four ordered stages. Nothing reads a claim before the signature over that claim
is verified.

1. **Read the unverified header for `kid`.** Attacker-controlled input, safe only
   because it selects from a key set we fetched ourselves and can never introduce
   one.
2. **Resolve `kid` to a public key.** From Django's cache; on a miss, fetch. If
   the `kid` is still absent, refetch once past the cache, because Apple rotates.
3. **Verify the RS256 signature**, with `algorithms=["RS256"]` passed explicitly.
4. **Check the claims.** `iss`, `aud`, `exp` and a `require` list via PyJWT;
   `nonce` compared afterwards so it gets its own error code.

```python
@dataclass(frozen=True)
class AppleIdentity:
    subject: str        # the `sub` claim; the join key, never the email
    email: str | None


def verify_apple_identity_token(token: str, *, expected_nonce: str) -> AppleIdentity:
```

Two deliberate deviations from the ticket's wording:

- **Returns a frozen dataclass, not the raw claim dict.** A dict invites MAC-27
  to reach for `email_verified` (Apple documents it as always true, so it carries
  no information) or `real_user_status`, neither of which doc 02 has a column for.
  The dataclass makes the two fields we use the only fields available, and it
  matches `PresignedUpload` in `uploads/services.py`.
- **`expected_nonce` is keyword-only and required.** An optional nonce is a
  replay check that quietly stops running the first time a caller forgets it.

`leeway=30s` on expiry. Zero leeway means a one-second clock skew between Railway
and Apple rejects a legitimate sign-in, and Apple's identity tokens are
short-lived anyway.

### 4. The amplification guard

A plain "unknown `kid` → refetch" rule means an attacker sending a thousand
tokens carrying `kid: "bogus"` makes the API send a thousand requests to Apple.
The cache does not help, because a forced refetch is precisely a cache bypass.

So the refetch takes a cooldown lock. `cache.add()` writes only when the key is
absent and reports whether it did, which makes it a lock with a built-in expiry
and no cleanup path. One refetch per five minutes regardless of traffic. A
genuine rotation is delayed by at most that window, well inside the overlap Apple
leaves when publishing a new key.

Generalisable: any "on miss, go fetch" path reachable by an untrusted caller has
this shape. The cache protects the happy path and does nothing for the miss path,
which is the one an attacker picks.

### 5. Errors

Every rejection raises DRF's `ValidationError` with a distinct `code`. Tests
assert on the code, because a suite where every bad input raises the same generic
error cannot show that the `aud` check does anything.

**MAC-27 must flatten all of them into one generic 401.** A response that
distinguishes "wrong audience" from "bad signature" is a free oracle for anyone
probing the endpoint. Written into doc 04 so it is not lore.

## Tests — `accounts/tests/test_apple_identity.py`

27 tests. One 2048-bit RSA keypair generated per session, tokens signed with it,
`_fetch_jwks` replaced by a call-counting stub. Real signature verification over
fake credentials, zero network — the same trick `uploads/tests/test_presign.py`
uses to sign real URLs against a fake R2. An autouse fixture clears the cache, or
LocMemCache leaks JWKS state between tests and the call-count assertions go
order-dependent.

| Input | Code | Proves |
| -- | -- | -- |
| Correct token | — | Returns subject and email |
| Second verification | — | Cache hit; Apple is not consulted per sign-in |
| No `email` claim | — | Succeeds with `email=None`, per doc 04 |
| Signed by another keypair, same `kid` | `invalid_signature` | The signature is verified, not merely parsed |
| Hand-forged HS256 using the public key as the HMAC secret | `invalid_signature` | Algorithm confusion fails |
| `aud` of another app | `invalid_audience` | Another app's Apple token is refused |
| Lookalike `iss` | `invalid_issuer` | Issuer is pinned |
| `exp` in the past | `token_expired` | Expiry enforced |
| Each of `aud`/`iss`/`exp`/`sub` absent | `missing_claim` | An absent claim is a failure, not a skipped check |
| Wrong nonce | `nonce_mismatch` | A captured token cannot be replayed |
| Absent nonce claim | `nonce_mismatch` | Missing is not matching |
| Raw nonce in the claim | `nonce_mismatch` | Guards the MAC-30 contract |
| Unknown `kid` | `unknown_key` | Fetcher called exactly twice |
| Rotated key | — | The refetch picks up Apple's new key |
| 20 junk `kid`s in a row | `unknown_key` | Fetch count stays at two; the lock holds |
| `""`, `not-a-jwt`, `only.two`, `a.b.c`, `...`, `Bearer …` | `malformed_token` | Garbage never reaches the crypto path |
| Header with no `kid` | `malformed_token` | No defaulting to some key |
| Empty `APPLE_CLIENT_ID` | `ImproperlyConfigured` | Misconfiguration fails loudly, not silently |
| JWKS unreachable | `jwks_unavailable` | An Apple outage is not a silent pass |

The HS256 test assembles the token by hand rather than with `jwt.encode()`, which
refuses to use a PEM as an HMAC secret. That refusal is PyJWT protecting the
*signing* side; an attacker has no such scruples and simply concatenates the
segments. Using the library's own guard would have made the test prove nothing.

## Alternatives rejected

| Option | Why not |
| -- | -- |
| PyJWT's `PyJWKClient` | The closest call. Fetches and caches JWKS for you, but into its own per-process LRU rather than Django's cache, and "exactly one refetch, then cool down" is not expressible through it. Also makes the network call harder to stub, which costs the hermetic suite |
| `django-allauth`'s Apple provider | Brings a full social-account model layer and its own opinions about user creation, to replace one function. It would own the sign-in flow MAC-27 is meant to write |
| Apple's `/auth/token` server-to-server | Needs a client-secret JWT built from `APPLE_PRIVATE_KEY` and adds a network round trip on the sign-in path. Designed for the web code-exchange flow, not a native identity token we can verify locally |
| Pin Apple's public keys in settings | Breaks on the first rotation, at a time nobody chooses, with no warning |
| Fetch JWKS per request | Puts Apple on the critical path of every sign-in and invites rate limiting |
| `requests` / `httpx` | Neither is a dependency. One call per day per worker, so pooling buys nothing. `urllib.request` with an explicit timeout is stdlib and trivially stubbable |

## Concepts in play

- **Asymmetric vs symmetric signing.** Apple signs with a private key we never
  see and publishes the public half, so there is no shared secret to leak or
  rotate. The JWKS machinery is the cost of that.
- **Why the token names its own key.** `kid` lets Apple rotate without
  coordinating with every relying party, at the price of every relying party
  needing refetch logic.
- **`cache.add()` as a lock.** Write-if-absent is the useful bit, and it is the
  same primitive behind most rate-limiting and idempotency work.
- **Algorithm confusion.** Why an explicit `algorithms` allowlist is mandatory,
  and why the hole exists at all.
- **What each claim defends.** `iss` against a lookalike issuer, `aud` against
  reuse across apps, `exp` against an old capture, `nonce` against replay.
- **This is every federated identity integration.** Google, Okta and Auth0 are
  the same four stages with different URLs.

## Blast radius

- Nothing imports `accounts/services.py`. It is new and has no callers until
  MAC-27.
- No model change, so no migration, so the deploy does nothing to the database.
- No view and no route, so `openapi.json` is unchanged. `pnpm generate:api` was
  run and produced a zero diff, as it must.
- The `CACHES` block replaces an implicit default with the identical explicit
  one. No behaviour change.

## Deliberately unhandled

- **Rate limiting the auth endpoint**, which doc 04 requires. There is no
  endpoint here; it belongs to MAC-27.
- **Apple's server-to-server calls.** `APPLE_TEAM_ID`, `APPLE_KEY_ID` and
  `APPLE_PRIVATE_KEY` stay unread. The MVP never revokes through Apple.
- **A shared cache across workers.** No Redis service exists and the bound is
  acceptable.
- **Replay beyond the nonce.** No `jti` tracking.
- **Unused claims.** `real_user_status`, `is_private_email`, `transfer_sub`.
- **Verifying the JWKS response itself.** TLS to `appleid.apple.com` is the trust
  anchor, which is how every OIDC client works.

## For the reviewer

Look hardest at:

- **The exception ordering in `verify_apple_identity_token`.** `InvalidSignatureError`
  subclasses `DecodeError`, so that clause has to come first or it is dead code.
  This is the kind of thing that silently degrades an error code rather than
  failing a test.
- **The nonce contract**, because it binds MAC-30 and is the one thing here that
  a later ticket can get wrong in a way that looks like a server bug.
- **The cooldown window.** Five minutes is a guess balanced between rotation
  latency and amplification. It is defensible, not measured.
