# MAC-27 — POST /api/auth/sessions/

Approved 20 Aug 2026. Linear:
[MAC-27](https://linear.app/hintology/issue/MAC-27/post-apiauthsessions-sign-in-account-resolution-and-reactivation).

## Context

The endpoint that turns a verified Apple token into a user and a JWT pair.
Registration and login are the same call, which is why the resource is a session
rather than a user: the client does not know, and does not need to know, whether
this person existed a moment ago.

Consumes MAC-26's verifier and MAC-34's `Identity` table. This ticket is
identity resolution, not cryptography.

**The spec was rewritten before implementation.** Three parts of the original
were wrong. Reasoning below and in the Decision Log.

## Three corrections to the original spec

### 1. The 30-day reactivation window is gone

**Was:** restore inside 30 days, refuse past it with a distinct error.
**Now:** restore, always. No date arithmetic on the sign-in path.

The refuse branch was unreachable in a working system. Past 30 days the purge
has already deleted the row, so reaching that branch means MAC-29's command is
broken, and a user-facing error is the wrong response to a broken cron.

It also served nobody. The person is trying to come back, and telling them to
return later, about data scheduled for destruction, helps neither side.

The deeper mistake was conflating two decisions that happened to share a number.
A purge grace period is a data-retention policy. A reactivation deadline is a
product rule. Welded together, changing one silently changes the other.

The purge still enforces the deadline, by deleting the row. Once it has, sign-in
takes the ordinary create branch. Removing the window deleted a branch, a date
comparison, a boundary test, and an error state.

Generalisable: **when a rule's only reachable failure mode is "our own
infrastructure is broken", it is monitoring, not product logic.**

### 2. The name is stored, and it cannot be verified

Doc 04 said no name is stored. Reversed, and not because a use for it appeared.
The asymmetry decided it: Apple sends `fullName` on the first authorization and
never again, so not capturing it is permanent. Same argument that decided
`real_user_status` in MAC-34, and worth stating as a rule — **for data available
exactly once, "nothing reads it yet" is a much weaker argument than usual.**

The constraint that shaped the implementation: Apple puts **no name claim in the
identity token**. Confirmed against their live discovery document, which lists
every claim they send:

```
aud, email, email_verified, exp, iat, is_private_email,
iss, nonce, nonce_supported, real_user_status, sub, transfer_sub
```

`fullName` is client-side only. So unlike email there is no verified alternative
to prefer, and the client's word is all there is. Acceptable for a display name,
documented at the field as never acceptable for anything security-relevant, and
`name` is deliberately not a member of `AppleClaims` so the boundary between
signed and unsigned data stays visible in the type.

`blank=True, default=""` rather than nullable. A nullable `CharField` gives two
ways to say "empty" and every reader then has to handle both.

### 3. Throttling is burst plus sustained

One flat rate has to choose between blocking a human who taps twice and leaving
room for a script. 10/min alone permits 600/hour; 60/hour alone rejects the
second tap in a minute. Two scopes, both of which must pass, express "a burst is
fine, all day is not".

Stated in the module docstring because it is easy to get backwards: **the
throttle is not the security control here.** Sign in with Apple has no password
to guess, and forged tokens are stopped by the signature check in MAC-26. This
limit exists for cost and denial of service, which is why it can afford to be
generous.

## Resolution

Lookup is `(provider="apple", subject=sub)` on `Identity`, with
`select_related("user")`, inside `transaction.atomic`.

| Found | Do |
| -- | -- |
| No identity | Create user + identity via `create_apple_user`, passing both Apple claims and the name |
| Identity, live user | Log in. Write email and name **only when present** |
| Identity, soft-deleted user | Restore: clear `deleted_at`, set `is_active=True`. No window |

Every branch ends by calling `record_authentication()`, which is what finally
makes `last_login` mean something.

**Absence is not a change.** Apple omits the email claim for real users and
never resends the name after the first authorization. Writing those absences
through would erase a working address on somebody's second login — a bug that
cannot appear until a real user comes back, and is unrecoverable once it does.

This is now the third rule of that shape in `accounts/`.
`record_authentication` refreshes `is_private_email` and deliberately never
touches `real_user_status`. They look collapsible. They are not, and the tests
say so.

## Two DRF traps, both measured

### `authentication_classes = []` turns a 401 into a 403

This endpoint must opt out of the project's `IsAuthenticated` default, because
it is the request that creates the session. But DRF rewrites
`AuthenticationFailed` and `NotAuthenticated` to **403** when the view has no
authenticator to build a `WWW-Authenticate` header from:

```
authentication_classes = []  -> 403
default auth classes         -> 401
```

So `InvalidAppleCredential` is a plain `APIException` subclass with
`status_code = 401`, which that rewrite does not touch. Rejected the alternative
of overriding `get_authenticate_header`, which fixes the status by advertising a
bearer challenge the endpoint does not actually issue.

This also corrects doc 04, which after MAC-26 claimed this endpoint "collapses
every one of them into a single generic 401" without noting that the obvious way
to do that yields 403. `test_rejection_is_401_and_not_403` is the regression
guard.

### A settings override that silently does nothing

`SimpleRateThrottle.THROTTLE_RATES` is a **class** attribute bound to the
settings dict at import time. Overriding `settings.REST_FRAMEWORK` in a test
creates a new dict the class never looks at, so the first throttle tests ran at
the real rate and passed while asserting nothing.

Production is unaffected: the class body runs after settings are configured, so
it binds the real rates. The tests patch `THROTTLE_RATES` on the throttle
classes instead.

The general shape is worth more than the instance. **A settings override that
silently does nothing produces a green test.** Any framework value captured at
import rather than read per call has this property, and the only reliable tell
is a test that fails when you break the thing it claims to cover.

## Files touched

| Path | Change |
| -- | -- |
| `accounts/models.py` | `User.name` |
| `accounts/migrations/0004_user_name.py` | Additive, one column |
| `accounts/services.py` | `InvalidAppleCredential`, `ResolvedSession`, `resolve_apple_user` |
| `accounts/serializers.py` | **New.** Request and response shapes |
| `accounts/views.py` | **New.** `SessionCreateView` |
| `accounts/urls.py` | **New.** Mounted at `/api/auth/` |
| `accounts/throttles.py` | **New.** Two scopes |
| `config/urls.py` | One `include()` |
| `config/settings/base.py` | `DEFAULT_THROTTLE_RATES` |
| `accounts/tests/test_sessions.py` | **New.** 30 tests |
| `packages/api-client/*` | **Regenerated and committed.** First real route |

## Tests

199 in the suite, 30 new. The verifier is stubbed rather than re-exercised — it
has 49 tests of its own, and this ticket is about what happens after it returns.

Two carry most of the weight:

- **A second sign-in with no email and no name leaves both stored values
  alone.** The bug doc 04 warns about.
- **Every distinct verification failure produces an identical response.** Nine
  codes, parametrised, all asserting the same body. A 401 that separates "wrong
  audience" from "bad signature" is a free oracle for anyone probing.

Also: reactivation with no time limit, a purged user getting a clean account,
both throttle scopes firing independently, a throttled request creating nothing,
and the minted access token resolving back to the right user.

That last one goes through `JWTAuthentication` directly rather than calling
another authenticated endpoint. The only ones that exist are uploads, which
would drag boto3 and R2 credentials into a test about tokens — the first attempt
did exactly that and failed on a missing endpoint URL, which looks nothing like
the real subject of the test.

## Blast radius

- **First real route in the generated client.** `pnpm generate:api` produces a
  diff here, unlike every previous auth ticket, and it is committed in the same
  PR or the drift job fails.
- **`operation_id="createSession"`** is permanent in practice. Left to generate
  it becomes `useApiAuthSessionsCreate`, and renaming later churns every call
  site in the mobile app.
- **The migration is additive**, one column with a default. Safe on a live
  table, unlike MAC-34's.
- **`APPLE_CLIENT_ID` becomes load-bearing in production with this merge.**
  MAC-26 made an empty value raise rather than silently pass, and this is the
  first ticket where a real user reaches that path. **Set it in Railway before
  merging.**
- **MAC-31 must exempt this route and `sessions/refresh/`** from its global 401
  retry handler. Firing it here means trying to refresh a session that does not
  exist yet.

## Deliberately unhandled

- **Refresh, sign-out, `/api/users/me/`.** MAC-28.
- **Setting `deleted_at`.** MAC-29. This ticket only reads it.
- **A shared throttle across workers.** No Redis. It lands on the per-process
  `LocMemCache` MAC-34 documented, so the limit is per gunicorn worker and
  resets on deploy. Acceptable for MVP; E8 owns the real fix.
- **Account merging.** One Apple ID is one user.
- **Replay beyond the nonce.** No `jti` tracking, unchanged from MAC-26.

## For the reviewer

- **The three "absence is not a change" rules**, which look collapsible and
  are not. Collapsing them erases a user's email on their second login.
- **`InvalidAppleCredential` being an `APIException` and not
  `AuthenticationFailed`.** It looks like the wrong base class until you know
  about the 403 rewrite.
- **The throttle numbers**, 10/min and 60/hour. Reasoned, not measured, same as
  MAC-26's cooldown.
