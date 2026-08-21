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

`get_or_create` rather than `create` on the blacklist row. A token blacklisted
by an earlier sign-out is still an outstanding row, and `create` would raise on
the unique constraint inside the transaction and roll the entire deletion back —
so signing out and then deleting, which is a completely ordinary sequence, would
fail. A test holds that case.

### 3. Deleting twice is a no-op, and returns 204 anyway

`delete_account` returns early if `deleted_at` is already set, so a retry cannot
push the timestamp forward. That column is the input to a retention deadline;
silently extending it is the kind of bug nobody notices until a purge fails to
purge.

The endpoint answers 204 either way. A 404 on the second call would report
failure for a request that got exactly what it asked for. The return flag exists
for logs and tests, not for the response.

In practice the second call is unreachable through HTTP — the account is
deactivated, so authentication rejects it first. The idempotency test therefore
calls the service directly, and the unreachability is itself asserted by the
test above it.

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

**Function-local import.** The blacklist models are imported inside
`delete_account` rather than at module scope. That app is only in
`INSTALLED_APPS` because `BLACKLIST_AFTER_ROTATION` needs somewhere to write; a
top-level import would make the whole module fail to load if it were ever
removed. This is the right call when a dependency is genuinely optional, and the
wrong call as a general habit — a local import hides a dependency from anyone
reading the imports.

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

## For review

* **The 204 on a repeat delete.** Defensible either way; the argument for it is
  above. Worth a second opinion since it is the one place the endpoint's
  behaviour is a judgement call rather than a consequence
* **The endpoint description promises restoration with no deadline.** True today
  and true after the purge ships, since the purge deletes the row and sign-in
  then takes the create branch. Flagged because it is a user-visible promise
  made in a schema description
