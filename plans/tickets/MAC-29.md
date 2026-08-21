# MAC-29 — account deletion (soft delete)

Implemented 21 Aug 2026. Linear:
[MAC-29](https://linear.app/hintology/issue/MAC-29/account-deletion-and-the-purge-command).

## Context

Both app stores refuse an app that creates accounts with no in-app way to remove
them, which is what makes this a release blocker for E9 despite sitting late in
E2. This ticket closes the sixth and last endpoint doc 04 specifies.

```
DELETE /api/users/me/    soft-delete the caller's account    authenticated
```

## Amendment, 21 Aug 2026: the purge is cut

The ticket originally shipped two things — the soft delete and a
`purge_deleted_users` management command on a Railway cron that hard-deletes at
30 days and sweeps R2 by prefix. The purge is now a follow-up.

The reasoning is about when the work becomes real. The purge is the half with
the infrastructure in it: a management command, a cron schedule, a paging delete
loop against an S3-compatible API, and a deployment doc change. None of it can
run correctly until 30 days after the first real deletion. The store requirement
holding up the release is the in-app deletion path, and that is entirely the
soft-delete half.

Nothing is thrown away by waiting. R2 keys are already namespaced
`pending/{user_id}/…` and `entries/{user_id}/…`, so the purge stays a prefix
sweep whenever it lands.

**One wording change follows from the cut.** The original acceptance criteria
had the endpoint describe the deletion as "reversible for 30 days". With no
purge running, that is false in both directions: nothing destroys the account at
30 days, and reactivation already has no time limit (MAC-27, doc 04). The
description says what is true — signing in again restores the account — and
names no deadline the system does not enforce.

## Files touched

| File | Change |
| -- | -- |
| `accounts/services.py` | new `delete_account(user)` |
| `accounts/views.py` | `delete()` on the existing `CurrentUserView` |
| `accounts/tests/test_account_deletion.py` | new, 12 tests |
| `packages/api-client/{openapi.json,src/endpoints.ts}` | regenerated |

No migration. `deleted_at` and `is_active` have been on the User model since
migration 0001.

## The decisions worth arguing about

### 1. Three writes, because each one closes a different hole

`deleted_at` records the deletion for the purge that does not exist yet. On its
own it stops nothing — no authentication path reads that column, so a
soft-delete implemented as that write alone leaves a fully working account.

`is_active=False` is what actually locks the account out. simplejwt's
`JWTAuthentication` checks the flag on every request, so the access token the
client is still holding fails on its next use rather than lasting out its
15-minute lifetime. This is the ticket's headline gotcha and it is easy to
miss, because the test that catches it has to reuse the token after the delete.

Blacklisting the outstanding refresh tokens closes the other path, and it fails
for a different reason. Refresh is a token exchange — it does not authenticate
the user, so `is_active` never enters into it. Without the blacklist a stored
refresh token keeps minting access tokens forever.

The two guards are independent, which is the point. Either one alone leaves a
usable way back into a deleted account.

### 2. Revocation is driven from the user, not from a presented token

Sign-out (MAC-28) blacklists the one refresh token in the request body. Deletion
cannot work that way: a DELETE carries no body, a user can be signed in on more
than one device, and "delete my account but stay signed in over there" is not a
thing anyone means. So the sweep is `OutstandingToken.objects.filter(user=user)`.

The revocation lives in `revoke_refresh_tokens`, which deletion and
reactivation both call. It is two queries, not one per token, and the review is
what got it there. `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` are both on, so
every refresh mints a new `OutstandingToken`, and nothing in this repo runs
`flushexpiredtokens`. A long-lived account therefore arrives with hundreds of
rows, most already blacklisted. The first version issued a `get_or_create` per
row inside the transaction, and that cost grows for as long as the user stays
signed in.

`bulk_create` with `blacklistedtoken__isnull=True` skips the rows an earlier
sign-out already revoked, and `ignore_conflicts=True` covers the row a
concurrent sign-out inserts between the SELECT and the INSERT. Either one alone
is enough for the ordinary case; both together mean the unique constraint cannot
raise and roll the whole deletion back. A test holds the sign-out-then-delete
sequence, which is the ordinary way to reach an already blacklisted row.

### 3. Deleting twice is a no-op, and returns 204 anyway

`delete_account` returns early if `deleted_at` is already set, so a retry cannot
push the timestamp forward. That column is the input to a retention deadline;
silently extending it is the kind of bug nobody notices until a purge fails to
purge.

**The guard re-reads the row under `select_for_update`**, which the review
caught and the first version got wrong. `request.user` is a snapshot loaded by
`JWTAuthentication` when it authenticated the request, so reading `deleted_at`
off it says what was true then. Two DELETEs arriving together would each read
None from their own stale copy, both pass the check, and the second would move
the timestamp. The lock makes the second one block and then read what the first
one wrote. A conditional `filter(...).update(...)` closes the same race in one
query and no lock; the lock won because it leaves a fresh row to write through,
where the conditional update returns a count and leaves the in-memory user
disagreeing with the database.

The endpoint answers 204 either way. A 404 on the second call would report
failure for a request that got exactly what it asked for. The return flag exists
for logs and tests, not for the response.

In practice the second call is unreachable through HTTP — the account is
deactivated, so authentication rejects it first. The idempotency test therefore
calls the service directly, and the unreachability is itself asserted by the
test above it.

### 3b. Reactivation revokes as well as restores

A second Copilot pass raised a race: a refresh landing between the SELECT and
the INSERT inside the sweep rotates to a token whose row nothing blacklisted.
The race is real. The consequence it named is not, and the fix it proposed
already exists.

simplejwt 5.5.1's `TokenRefreshSerializer` applies `USER_AUTHENTICATION_RULE` to
the token's user before it rotates anything, and the default rule is
`is_active`. So a token that escapes the sweep gets a 401 on refresh anyway,
with `no_active_account`. Measured, not assumed — the endpoint answers 401 while
the account is deleted.

What the same measurement exposed is a real gap one step further on. `is_active`
is the only thing holding that token down, so **reactivation is where it comes
back to life**: after `resolve_apple_user` clears the flag, the escaped token
refreshes successfully. So reactivation now calls `revoke_refresh_tokens` too. A
restore must not re-arm a credential issued before the deletion.

Scoped to the reactivation branch, not to every sign-in. Signing in on a second
device must not sign the first one out; only a restore means "nothing issued
before now is still good". A test holds each half.

Closing the race itself would mean `select_for_update` on the user row in the
refresh path — a lock on the hottest endpoint in the API to protect a window two
statements wide, when the window already fails closed. Not worth it.

### 4. Identities are left alone

Soft delete is a property of the person. `resolve_apple_user` restores the
account by finding the Identity row for the same Apple `sub`, so deleting it
here would turn every return visit into a brand-new account — and would collide
with the unique `(provider, subject)` constraint on the way. Doc 04 states this
directly; a test pins it, and a second test drives the restore through
`resolve_apple_user` so the seam with MAC-27 cannot break silently.

### 5. `DELETE` lives on `CurrentUserView`, not a view of its own

It acts on the same row `GET` and `PATCH` do. `GET /api/auth/me/` beside
`DELETE /api/auth/account/` was one entity under two names, which is what the
20 Aug 2026 route audit removed. The class docstring now says so, replacing the
line that pointed forward to this ticket.

## Django and DRF concepts in play

**Soft delete.** A column marks the row dead and every read path has to agree to
respect it. That is the cost, and it is why this codebase keeps the number of
readers small: `is_active` does the enforcement through machinery that already
exists, and `deleted_at` is left as pure record-keeping. A soft delete that
invents its own manager or query filter has to be right in every future query;
this one has to be right in zero.

**`update_fields` on save.** `user.save(update_fields=[...])` writes two columns
instead of every column on the model. It is not only a performance habit — a
full save writes back whatever the in-memory instance holds, which quietly
clobbers concurrent updates to fields this code never meant to touch.

**Row locking.** `select_for_update()` adds `FOR UPDATE` to the SELECT, and
Postgres holds that lock until the surrounding transaction commits. It only
means anything inside `transaction.atomic()`, and it is the standard answer to
read-then-write on a row two requests can reach at once. The read has to be
inside the lock: locking a row and then trusting a value read before the lock
protects nothing.

**Where a Django import goes.** The first version imported the blacklist models
inside the function, arguing that a top-level import would break the module if
`token_blacklist` ever left `INSTALLED_APPS`. The review took that apart, and it
was right — if the app were removed, `delete_account` is broken either way,
because the models it queries are gone. The local import only converts an import
error at startup, which CI and every deploy catch, into a 500 while a user is
deleting their account. The genuine reason for a function-local Django import is
app-registry ordering, for modules imported during `AppConfig.ready()`; a
`services.py` imported from a view runs long after that. Moved to module scope.

## Blast radius

Small. One new method on an existing view, one new service function, no
migration, no change to any existing code path. The generated client gains
`deleteCurrentUser` and loses nothing.

The one thing to watch: this endpoint is now the only way an account leaves the
system, and nothing removes data. That is deliberate for now and it is stated in
the endpoint description, but it is also a growing pile that the follow-up purge
ticket has to clear.

## Deliberately unhandled

* The `purge_deleted_users` command, the Railway cron, and the doc 09 change
* R2 object deletion, at delete time or ever. Photos must survive the window, or
  a restored account comes back empty
* A confirmation step. That is the mobile client's job, not the API's
* Any admin view of deleted users beyond the `deleted_at` column the admin
  already shows

## What the review changed

Four things, and three of them were mine to get wrong.

* **The blacklist loop was an N+1** that grows with how long the user has been
  signed in. Now `bulk_create` with `ignore_conflicts`
* **The idempotency guard read a stale instance.** Now `select_for_update` and a
  re-read inside the transaction, with a test that reproduces the stale copy
  without needing two threads
* **The function-local import did not buy what its comment claimed.** Moved to
  module scope
* **The endpoint description promised restoration with no deadline.** True
  today, false the day the purge ships — and wrong in `openapi.json`, in the
  generated client, and in any app copy lifted from it. It now states the
  mechanism and treats the deadline as a variable: restoration works "as long as
  the account has not yet been purged". It also no longer promises a 204 on a
  repeat delete, because a deactivated account gets a 401 from authentication
  before the view runs

A second automated pass then raised the refresh-versus-delete race, which is
covered above: the race is real, its stated consequence is not, and it exposed a
genuine gap at reactivation instead.

The 204 on a repeat was reviewed and kept. It is close to unreachable over HTTP
for that same reason, so the status is really only the answer `delete_account`
gives its own caller.
