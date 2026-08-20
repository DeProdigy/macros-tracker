# MAC-25 — Auth foundations: simplejwt and the User model under Apple-only

Approved 20 Aug 2026. Linear:
[MAC-25](https://linear.app/hintology/issue/MAC-25/auth-foundations-simplejwt-and-the-user-model-under-apple-only).

## Context

E2 is Sign in with Apple only (doc 04). Two things have to be true before any
auth endpoint can exist, and neither is true today:

1. The project cannot issue or verify JWTs. `DEFAULT_AUTHENTICATION_CLASSES` is
   session auth alone, which works for the Swagger UI and for nothing a native
   client does.
2. `accounts.User` is still shaped for email/password. `email` is `NOT NULL`,
   and `is_email_verified` exists for a verification flow doc 04 deleted. Apple
   users may hide their address, so a required email makes the sign-in path in
   MAC-27 impossible to write.

This ticket does the settings and the model, and stops there. No endpoints, no
views. MAC-27 and MAC-28 build on it. Splitting it this way puts the destructive
migration in a PR that can be reviewed on its own and deployed on its own,
rather than riding along with a behaviour change.

`accounts_user` is empty in production (confirmed in MAC-24), so dropping a
column costs nothing right now and will not stay that way.

## Approach

### 1. Dependency

`uv add "djangorestframework-simplejwt"`, run from `apps/api`. Commit
`pyproject.toml` and `uv.lock` together. CI runs `uv sync --locked`, so a stale
lockfile fails the `python` job.

No `pyjwt[crypto]` here. RS256 is MAC-26's problem; simplejwt signs our own
tokens with HS256 off `SECRET_KEY` and needs nothing extra.

### 2. Settings — `config/settings/base.py`

Add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS`. Its
migrations ship with the package and create `OutstandingToken` /
`BlacklistedToken`; nothing of ours needs generating for them.

New `SIMPLE_JWT` block:

```python
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
```

Hardcoded, decided at the gate. Unlike the R2 expiries a few lines above, a token
lifetime is a security decision rather than a per-environment fact, so changing
one should cost a commit and a review. Env-tunable would let production drift to
a 90-day refresh through a Railway variable nobody reviewed. `.env.example` gains
no new vars.

**Why 15 minutes and 30 days.** Nothing checks a blacklist on the access path,
so an access token is unrevokable for its whole life. That is the entire
argument for keeping it short. Longer access tokens buy fewer refresh
round-trips, which is not a problem this app has. Going much shorter than 15
minutes means a user who backgrounds the app for a coffee gets a refresh on
every return, which is a wasted round-trip and a 401 to handle on flaky mobile
data. 30 days on the refresh token is what stops a normally-active user ever
seeing the sign-in screen again.

**Signing key.** simplejwt defaults `SIGNING_KEY` to `SECRET_KEY`. Leave it, but
comment it: rotating `DJANGO_SECRET_KEY` in Railway signs every user out. That
is a footgun worth writing down next to the setting, not discovering during an
incident.

Reorder `DEFAULT_AUTHENTICATION_CLASSES`:

```python
"DEFAULT_AUTHENTICATION_CLASSES": [
    "rest_framework_simplejwt.authentication.JWTAuthentication",
    "rest_framework.authentication.SessionAuthentication",
],
```

Session auth stays underneath so `/api/docs/` still works against a logged-in
admin session. Order matters for more than precedence: DRF takes the 401
challenge header from the *first* authenticator, so anonymous requests start
returning `401 Bearer realm="api"` instead of `403`.

### 3. Model — `accounts/models.py`

- `email = models.EmailField(unique=True, null=True, blank=True)`. Unique
  survives because Postgres treats NULLs as distinct, the same trick
  `apple_user_id` already relies on. Ruff's DJ001 (nullable string field) exempts
  `unique=True`, which is why the existing `apple_user_id` passes today.
- Drop `is_email_verified`.
- Add `UserManager.create_apple_user`:

```python
def create_apple_user(self, apple_user_id, email=None, **extra_fields):
    if not apple_user_id:
        raise ValueError("Apple users must have an apple_user_id.")
    user = self.model(
        apple_user_id=apple_user_id,
        email=self.normalize_email(email) if email else None,
        **extra_fields,
    )
    user.set_unusable_password()
    user.save(using=self._db)
    return user
```

`create_user` is untouched. It hard-requires an email and always calls
`set_password`, which is correct for `createsuperuser`. Loosening it to fit
Apple would weaken superuser creation, so Apple gets its own entry point.

`set_unusable_password()` writes a `!` sentinel plus random noise into
`password`. `check_password` then returns `False` for every input including the
stored value, so there is no password to guess and no empty-hash edge case. It
is not the same as leaving the column blank.

- `__str__` has to change. With `null=True`, django-stubs types `self.email` as
  `str | None`, and `__str__` must return `str`, so mypy fails on the current
  body. Fix:

```python
return self.email or self.apple_user_id or f"user {self.pk}"
```

The f-string terminates the chain at a real `str`, and the fallback order is the
most useful thing to show in the admin.

#### Why nullable rather than required

Email is not identity here. Doc 04 makes `apple_user_id` (the `sub` claim) the
join key and says never to use email as one, since relay addresses change. A
`NOT NULL` email therefore buys no integrity, it only adds a way to fail.

And it does fail. Four ways, in rough order of likelihood.

1. The client reads `credential.email`, which is `nil` for every user who has
   signed in before. First-authorization-only is documented and deliberate. This
   is the common real-world cause, and it is a client bug rather than provider
   flakiness.
2. Hide My Email returns a `@privaterelay.appleid.com` address. Present, but the
   user can switch forwarding off, leaving an address that bounces.
3. Anomalous app-association state. Apple's forums carry repeated reports of
   tokens with a valid `sub` and no `email` claim, usually after a partial
   revocation. Outside our control, fixed only by the user re-authorizing.
4. Managed Apple IDs under Work & School, where `email_verified` can be false.

Under `NOT NULL`, MAC-27 gets two options in those cases: reject the sign-in,
locking a real user out permanently, or fabricate a placeholder, writing junk
into a unique column. `NULL` is better than both.

The general rule, which is worth carrying to any federated provider: the subject
identifier is the only field the provider guarantees. Every other claim is
optional and consent-gated. `NOT NULL` on a federated claim encodes an assumption
about someone else's consent UI into our database constraints.

Nothing reads the field anyway. A grep across `apps/api` returns two hits,
`create_user` writing it and `__str__` displaying it. No mail is sent, no
verification, no reset.

`create_user` and `create_superuser` keep hard-requiring an email, so
`createsuperuser` and the admin are unchanged. Only `create_apple_user` is
permissive.

#### Why `is_email_verified` goes rather than stays

Nothing reads it. The only references are the model, three spots in `admin.py`,
one test assertion, and migration `0001`.

The problem is what it would become. Under Apple-only nothing would ever set it
`True`, so every user sits at `False` forever, and the next person writing an
auth gate sees a field named `is_email_verified` and uses it. That locks out the
whole userbase. A column that lies is worse than an absent one.

The concept is dead upstream too. Apple documents the identity token's
`email_verified` claim as always `true`, because their servers only return
verified addresses. The single exception is Sign in with Apple at Work & School,
which does not apply. Keeping the column would mean storing a constant.

If email/password returns for a web client, re-adding a nullable boolean is a
trivial migration. Dropping a column once real users exist is not, and
`accounts_user` is empty in production right now.

### 4. Admin — `accounts/admin.py`

Not in the ticket, but mandatory: `is_email_verified` appears in `list_display`,
`list_filter`, and the Profile fieldset. Dropping the field without touching
these fails `admin.E108` at system-check time, which breaks every test and every
`manage.py` invocation, not just the admin page.

- `list_display`: `is_email_verified` becomes `apple_user_id`, which is now the
  join key and the more useful column.
- `list_filter`: drop it.
- Profile fieldset: drop it. `apple_user_id` is already there.

`accounts/forms.py` needs no change. I thought it did, on the theory that a
ModelForm turns empty input into `""` rather than `None`, which on a unique
column would collide across two staff-created users. Django already handles it:
`models.CharField.formfield()` sets `empty_value=None` whenever the field is
`null=True`, so the admin add form cleans a blank email to `None`. Checked
against Django 6.0.7.

### 5. Migration

One `makemigrations accounts` run produces one file with `RemoveField`
(`is_email_verified`) and `AlterField` (`email`). Read it before committing, do
not hand-edit it.

### 6. Regenerate the API client

**The ticket's acceptance criterion "`pnpm generate:api` produces no diff" is
wrong, and following it would fail CI.** drf-spectacular ships
`contrib/rest_framework_simplejwt.py`, whose `SimpleJWTScheme` registers against
`JWTAuthentication` under the name `jwtAuth`, so adding that authenticator adds a
security scheme.

I confirmed this rather than predicting it, by generating the schema against a
throwaway settings module with simplejwt installed as a `uv run --with` overlay.
`--fail-on-warn` still passes, and the diff against the committed file is exactly
five lines: a `jwtAuth` bearer scheme in `components.securitySchemes`, and
`{"jwtAuth": []}` added ahead of `cookieAuth` on `POST /api/uploads/`.

So: run `pnpm generate:api` and commit the diff. The `api-client-drift` job is
what would otherwise catch this. The reasoning goes in the PR description, since
it contradicts the ticket.

Orval's react-query output ignores security definitions, so I expect
`packages/api-client/src/**` to be unchanged and the diff to be confined to
`openapi.json`. If `src/**` does move, that is worth a second look rather than a
blind commit.

### 7. Tests

`accounts/tests/test_models.py`:

- Remove the `assert not user.is_email_verified` line from
  `test_create_user_sets_sensible_defaults`.
- `create_apple_user` sets `apple_user_id`, leaves `email` as `None`, and
  `has_usable_password()` is `False`.
- Two Apple users with no email coexist. This is the one that proves the NULL
  semantics rather than assuming them.
- Duplicate `apple_user_id` raises `IntegrityError`.
- `create_apple_user("")` raises `ValueError`, no DB marker needed.
- `create_apple_user` normalises an email when one is supplied.

New `accounts/tests/test_tokens.py`, small:

- `RefreshToken.for_user(user)` then `.blacklist()` succeeds and writes an
  `OutstandingToken` / `BlacklistedToken` row.

That last one exists to prove `token_blacklist` is actually in `INSTALLED_APPS`
and migrated. Without it, the app being missing is invisible until MAC-28 tries
to log someone out. Rotation behaviour itself belongs to MAC-28.

`uploads/tests/test_presign.py` needs no change. Its
`test_presign_requires_authentication` already asserts
`status_code in (401, 403)`, which absorbs the 403 to 401 shift from the
authenticator reorder.

### 8. Doc corrections in Linear

Two docs were wrong. Both fixed in Linear and re-mirrored with `pnpm sync:plans`,
since `plans/` is generated.

**Doc 02, Accounts block.** Lists `email unique` with no mention of nullable, and
says nothing about `is_email_verified`. After this ticket the model and doc 02
disagree. Should read `email unique, nullable` with a one-line why.

**Doc 04, line 43.** Says "Apple returns the user's name and email only on first
authorization. If you don't persist it then, you never get it again." That is
correct for the name and wrong for the email. Apple's documented behaviour is
that `fullName` and the credential object's `.email` property are
first-authorization-only, while the **verified email address is included in the
identity token on subsequent authorization requests**. The token is what MAC-26
parses, so the distinction is not academic.

This matters for MAC-27 in two ways. Email must be read from the verified token
claims rather than a client-supplied credential field, which is also the only
secure option since `credential.email` is unverified. And each sign-in must be an
upsert that never overwrites a stored address with null when the claim is absent.

Doc 02 also gained a note that no name field exists, deliberately. Nothing in
the product displays or greets by name, so Apple's one-shot `fullName` has
nowhere to go and loses nothing. That makes doc 04's first-integrator warning
inapplicable here rather than merely unheeded, which is worth stating so a
future reader does not 'fix' it by adding a column nothing reads.

A Decision Log entry dated 20 Aug 2026 covers the nullable decision, the dropped
flag, the doc 04 correction, and the rotation caveat.

## Alternatives rejected

**django-rest-knox.** Opaque tokens, SHA-hashed at rest, DB lookup per request,
instant revocation, logout is a delete. Better maintained than simplejwt right
now (5.1.0 in July 2026, declares Django 6.0). The argument for it is stronger
than it first looks: E2 wants revocation in three places, and once
`token_blacklist` is installed every refresh hits Postgres anyway, so we pay the
stateful cost and still cannot revoke an access token inside its 15 minutes.
JWT's statelessness pays off across many services sharing no database. This is
one Django process talking to one Postgres.

Rejected because doc 04 already made this call with reasoning attached, and
MAC-25's stated learning goal is the threat model behind rotation, which Knox
removes rather than teaches. Second reason, concrete: Knox ships no
drf-spectacular extension, so `--fail-on-warn` would need a hand-written
`OpenApiAuthenticationExtension`.

**django-allauth headless.** The most actively maintained of the three, and it
would subsume MAC-26 and MAC-27 outright, Apple token verification included. The
right answer if the goal were shipping auth. Wrong here, since Linear calls
MAC-26 the best learning ticket in the epic.

**Session cookies.** Doc 04 rejected these already. Simpler and safer in a
browser, awkward for a native client.

### On simplejwt's maintenance, since it looks alarming

Last release is 5.5.1, July 2025, with classifiers stopping at Django 5.2. That
is a fair thing to be nervous about on a Django 6.0.7 project, so I checked
instead of assuming. PR #959 ("add django 6.0 and python 3.14 support") merged
2026-02-09 and changed six files: CI workflow, tox, pre-commit, docs conf, and
setup.py classifiers. No source changes. Django 6 needed no code fix.

I then ran 5.5.1 against our Django 6.0.7 with `token_blacklist` installed and
the settings above applied. System checks clean, blacklist models import,
lifetimes resolve. It is in maintenance mode, not abandoned, and the surface it
covers barely moves.

### What rotation actually buys, precisely

Doc 04 says reuse of a blacklisted token "makes the theft detectable" and MAC-25
says the next use is "a signal rather than a silent compromise". Reading
`TokenRefreshSerializer.validate`, rotation blacklists the old token and mints a
new one. That is all it does. There is no family invalidation, no reuse
detection, and no signal emitted anywhere in the package.

So a stolen refresh token's reuse returns a 401 to the attacker. Nobody is
notified and the legitimate session keeps working. That is failure, not
detection. Detection is the OAuth family-invalidation pattern, where reuse of an
already-rotated token kills the whole family and forces a real sign-in. Worth
recording so the gap is a known follow-up rather than an assumed feature.

## Blast radius

Small but not zero. One migration dropping a column, on a table that is empty in
production. Every authenticated request now runs `JWTAuthentication` first,
which for a request with no `Authorization: Bearer` header is a cheap no-op that
falls through to session auth. The one visible behaviour change is anonymous
requests returning 401 rather than 403.

Merging deploys to Railway and runs the migration. Worth confirming
`accounts_user` is still empty at merge time rather than trusting MAC-24's
snapshot.

## Deliberately not handled

- Any endpoint. No `/api/auth/sessions/`, no view, no serializer.
- Apple token verification. MAC-26.
- Rate limiting the auth endpoint (doc 04 security requirements). Belongs with
  the endpoint in MAC-27.
- `UPDATE_LAST_LOGIN`. MAC-27 mints tokens directly rather than through
  simplejwt's `TokenObtainPairView`, so the setting would not fire anyway.
- Purging on `deleted_at`. MAC-29.

## Verification

From `apps/api`:

```
uv sync --all-groups
uv run python manage.py makemigrations accounts   # review the file
uv run python manage.py migrate
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --create-db
```

`--create-db` matters here: `--reuse-db` in `pyproject.toml` would skip the
migration and hide a broken one.

From the repo root:

```
pnpm generate:api        # expect an openapi.json diff, commit it
pnpm lint && pnpm check-types
```

Then, by hand: `uv run python manage.py createsuperuser` still works, the admin
add-user page saves a blank email as `NULL` rather than `""`, and `/api/docs/`
still authorises against that session.

Doc sync, after the Linear edits land:

```
pnpm sync:plans          # regenerates plans/02, plans/04, plans/decision-log
git diff plans/          # confirm only the intended lines moved
```

Finally, save this plan to `plans/tickets/MAC-25.md` and commit it, per the
working agreement in CLAUDE.md.
