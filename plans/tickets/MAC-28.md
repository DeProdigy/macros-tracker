# MAC-28 — session endpoints: refresh, sign-out and me

Implemented 20 Aug 2026. Linear:
[MAC-28](https://linear.app/hintology/issue/MAC-28/session-endpoints-refresh-sign-out-and-me).

## Context

The four endpoints that keep a session alive, end it, and report who is signed
in. With MAC-27's sign-in already shipped, this closes five of the six endpoints
doc 04 specifies; `DELETE /api/users/me/` is MAC-29's.

```
POST   /api/auth/sessions/refresh/   refresh -> new access + new refresh   AllowAny
DELETE /api/auth/sessions/current/   blacklist the presented refresh       authenticated
GET    /api/users/me/                the current user                      authenticated
PATCH  /api/users/me/                settings                              authenticated
```

## The three decisions worth arguing about

### 1. The settings columns did not exist, so this ticket adds them

`PATCH /api/users/me/` is specified to write goal weight, timeline, training
days and dietary constraints. Doc 02's schema has none of them, and no other
ticket owns them: doc 05 moved the four questions out of onboarding and doc 08
reads dietary constraints back, but nothing ever specified where they are
stored. The route cannot exist without the columns, so migration 0005 adds them.

Choices made here, none of which the plan docs settle:

* **Units in the field name.** `goal_weight_kg`, following `protein_g` and
  `fiber_g` in doc 02. A bare `goal_weight` is the column that eventually
  receives pounds from one call site and kilos from another
* **Weeks, not a target date.** A stored date goes stale on its own and then
  reads as a missed deadline. A duration means the same thing whenever it is
  read
* **All four nullable or blank, no defaults.** "Not answered" is the normal and
  usually permanent state for these. A default would be a fabricated answer, and
  target generation cannot tell a fabricated 3 training days from a stated one
* **Free text for dietary constraints, capped at 500.** It feeds an AI prompt,
  which reads "no dairy, allergic to shellfish" as well as it reads "vegan". An
  enum of diets has to be extended for every constraint a real person has
* **Bounds as model validators**, so the admin and the API reject the same
  values. DRF's `ModelSerializer` copies model validators onto serializer
  fields, so there is one place to change them

`timezone` is writable too, which the acceptance criteria did not list. Doc 02
says the client refreshes it on launch and no route had ever been specified to
accept it — the same gap that produced `PATCH` in the first place. Flagged for
review rather than left for a second ticket to add one field.

### 2. drf-spectacular drops request bodies on DELETE

The trap the ticket warned about was simplejwt's unannotated `TokenRefreshView`.
That one is real and the subclass handles it. This second one is not in the
ticket and is worse, because nothing fails.

`AutoSchema._get_request_body` returns `None` for any method outside PUT, PATCH
and POST. So `@extend_schema(request=SessionDeleteSerializer)` on a DELETE is
accepted, ignored, and produces a bodyless operation. Orval then generates
`deleteCurrentSession()` taking no argument, and the mobile client physically
cannot sign out through the generated client. No warning, no failed build,
`--fail-on-warn` green.

`accounts/schema.py` subclasses `AutoSchema` and lets DELETE take POST's path
through the base implementation. Applied to that one view rather than as the
project-wide `DEFAULT_SCHEMA_CLASS`: a global switch quietly blesses a DELETE
body everywhere, and the next one should have to make this argument again.

The body itself stays. RFC 9110 gives a DELETE body no defined semantics and
most of them are a mistake, but the alternatives here are worse — a query string
puts a live refresh token into every access log and proxy cache, and a custom
header invents a private protocol for one endpoint.

### 3. Read and write shapes are separate serializers

`UserSerializer` is fully read-only; `UserSettingsSerializer` lists the five
writable fields. The obvious alternative is one serializer with
`read_only_fields`, and the reason to refuse it is what failure looks like: a
client that can set its own `onboarding_completed` skips onboarding by sending
one extra key, and that hole ships the day somebody relaxes a `read_only_fields`
entry in a diff where nothing looks wrong.

`SessionUserSerializer` is gone, replaced by `UserSerializer` in the sign-in
response. Two serializers describing the same row generate two client types that
drift the first time a field is added to one of them — which is exactly what
adding four settings fields would have done.

## Refresh cannot require authentication

The deadlock is the concept in this ticket. The endpoint is reached *because* the
access token expired, so demanding a valid access token to obtain a new one
means an expired session is unrecoverable and the user signs in again. The
refresh token in the body is the credential.

`SessionRefreshView` inherits `TokenRefreshView`, which already sets both
`permission_classes` and `authentication_classes` to empty tuples. Stated
explicitly on the subclass anyway. Note the difference from `SessionCreateView`
and `PingView`, which spell it `AllowAny` because `APIView` gives them the
project default of `IsAuthenticated`; mypy rejects a list of permission classes
against simplejwt's `tuple[()]` annotation, so the subclass uses empty tuples.

The refresh *logic* is inherited deliberately. Rotation and blacklisting are a
security control, and reimplementing them to own the response shape would be
rewriting a security control for cosmetics.

## What sign-out does not do

Nothing on the access-token path consults a blacklist. Signing out blacklists the
refresh token, and the access token the client is already holding stays valid
until it expires — up to 15 minutes later. That gap is the reason the access
lifetime is short, and it is stated in the endpoint's own description so a
client author does not assume otherwise.

The ownership check on the presented token is not optional. Without it any
authenticated caller who gets hold of a refresh token can end that session:
denial of service on somebody else's account, dressed as a sign-out. The
comparison is between strings, because simplejwt stringifies the id when it mints
the claim — `payload["user_id"]` is `"42"` while `request.user.pk` is `42`, and a
naive `!=` makes *every* sign-out fail with "not your token", including the
legitimate one. Caught by a test rather than in review.

## Changed in review

Six comments on the PR. Four changed code.

**A 500 where a 401 belongs.** simplejwt's `TokenRefreshSerializer.validate`
looks the token's user up with a bare `.get()` (5.5.1, `serializers.py:116`), so
a valid refresh token whose user row is gone raises `User.DoesNotExist` straight
past DRF's exception handler. `SessionRefreshView.post` now catches it and
raises `AuthenticationFailed`. A token that outlived its user is a dead
credential, not a server fault.

The three delete-ish states behaved differently before this: `is_active = False`
gave a correct 401 through simplejwt's `USER_AUTHENTICATION_RULE`, a hard delete
gave a 500, and `deleted_at` alone gave a 200. The first two are now both 401 and
both pinned by a test. The third is MAC-29's, because nothing on this path reads
`deleted_at` yet.

**Refresh is throttled.** One scope at 20/min, where sign-in has two. Sign-in is
a human tapping a button, so a burst limit and a daily limit answer different
questions. Refreshing is a machine on a timer: one device needs about four calls
an hour against a 15-minute access lifetime. A single generous per-minute cap
catches the failure that happens here, which is a client stuck in a retry loop.
MAC-36's proxy problem weakens the limit and does not make it useless, which is
the same thing `throttles.py` already says about sign-in.

**A schema test, the project's first.** `RequestBodyOnDeleteAutoSchema` overrides
a private method. If drf-spectacular renames `_get_request_body`, the override
stops being called silently, and the only signal is `api-client-drift` going red
in generated TypeScript on an unrelated dependency bump. Three tests in
`test_schema.py` name the intent: the sign-out body exists, it is the refresh
token, and no other DELETE grew one.

**Two more lifecycle tests.** An expired but well-formed refresh token, which is
what happens to every user at 30 days and which the garbage-token test said
nothing about. And the deactivated user, so token revocation on deactivation is a
stated property before MAC-29 has to decide whether to lean on it.

Not changed: `goal_weight_kg` stays a `DecimalField`, so the wire format is the
string `"78.50"` and the mobile side parses before doing arithmetic. A JSON
number here is an IEEE double and `78.5` round-trips into `78.49999999999999`.
`dietary_constraints` stays free text. And `permission_classes` on the refresh
view stays an empty tuple rather than `[AllowAny]` — simplejwt annotates it as
`tuple[()]`, so every spelling of AllowAny needs a `type: ignore`, and two of
those to win a naming preference is the wrong trade.

## Files touched

| File | Change |
| -- | -- |
| `accounts/models.py` | four settings fields on `User` |
| `accounts/migrations/0005_user_settings_fields.py` | the migration |
| `accounts/serializers.py` | `UserSerializer`, `UserSettingsSerializer`, `SessionRefreshSerializer`, `SessionDeleteSerializer`; `SessionUserSerializer` removed |
| `accounts/views.py` | `SessionRefreshView`, `CurrentSessionView`, `CurrentUserView` |
| `accounts/schema.py` | new — `RequestBodyOnDeleteAutoSchema` |
| `accounts/throttles.py` | `RefreshThrottle` |
| `config/settings/base.py` | the `refresh` rate |
| `accounts/urls.py` | `sessions/refresh/`, `sessions/current/` |
| `accounts/urls_users.py` | new — `/api/users/me/` |
| `config/urls.py` | second mount for `accounts` at `/api/users/` |
| `accounts/admin.py` | Settings fieldset; `name` added to Profile |
| `packages/api-client/**` | regenerated |

## Tests

38 new, in `test_session_lifecycle.py`, `test_current_user.py` and
`test_schema.py`. The ones that carry weight:

* A rotated refresh token is **rejected on reuse**. Without this assertion,
  `ROTATE_REFRESH_TOKENS = True` proves only that the response contains a second
  string. Reuse of a rotated token is the observable signature of a stolen
  credential
* Refresh succeeds with **no `Authorization` header**, asserted with the header
  explicitly cleared. The deadlock is invisible in any test that happens to send
  one
* Sign-out **refuses another user's token**, and that token still works
  afterwards
* `PATCH` with an omitted field leaves it alone; `PATCH` with an explicit null
  clears it. The same request one key apart, which is what pins `PATCH`'s
  contract down
* `PATCH` cannot set `onboarding_completed` or rewrite `email`. Unknown keys are
  ignored rather than rejected, so this fails silently when it regresses
* `me` 401s with no token, and with a token backdated past its own expiry
* `PUT` is 405
* A refresh token whose user row was deleted returns 401, not 500. Verified by
  breaking the fix and watching the test go red
* The sign-out operation carries a `requestBody` in the emitted schema, and no
  other DELETE does

## Blast radius

The sign-in response body gains four fields, because it embeds the user. Additive
and typed, so existing clients are unaffected; the generated `SessionUser` type
is renamed to `User`, and apps/mobile does not reference it yet.

Migration 0005 is four nullable/defaulted `AddField`s on a table with no
production rows to speak of. No rewrite, no backfill.

## Deliberately unhandled

* **Soft-deleted users can still refresh.** `deleted_at` is not consulted
  anywhere in this ticket, so a soft-deleted user with a live refresh token keeps
  minting access tokens. MAC-29 owns setting it and blacklisting that user's
  outstanding tokens. Deactivation (`is_active = False`) already revokes, and
  there is now a test saying so
* **No session list.** A client cannot enumerate or revoke its other devices.
  `sessions/current/` is the only addressable session, and OutstandingToken has
  no device metadata to list anyway
* **Timezone strings are not validated against the IANA database.** Any 64
  characters are accepted, as before this ticket

## For the reviewer

1. `accounts/schema.py` — the DELETE-body override. It is the one place this
   ticket works around a library default rather than following it, and
   `test_schema.py` is what stops it failing silently
2. Whether `timezone` belongs in the writable set, given the acceptance criteria
   listed four fields and this ships five
3. The four new columns' names, units and bounds. They are the ones the E3
   target work will read, and renaming a column after the client generates from
   it is not free
4. `SessionUserSerializer` removal — a contract change to an endpoint that
   shipped three commits ago
