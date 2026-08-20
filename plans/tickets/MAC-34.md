# MAC-34 — Move identity off the User table into an Identity join table

Approved 20 Aug 2026. Linear:
[MAC-34](https://linear.app/hintology/issue/MAC-34/move-identity-off-the-user-table-into-an-identity-join-table).

## Context

`apple_user_id` lived on `User`. It moves to an `Identity` table, one row per
`(provider, subject)` pair. One destructive migration, no endpoints.

Prompted by reading a friend's production Supabase `auth.users` table, which
turned out to be a better source of design pressure than any amount of thinking
about it in the abstract.

I argued against this when it was hypothetical, on the grounds that a join table
for a provider that does not exist is speculative generality. That was wrong.
`accounts_user` is empty in production (MAC-24), so the change costs one
migration today and a backfill plus a deploy window after the first real user.
"Not yet" is only free when the cost curve is flat.

Its own ticket and its own PR, per the MAC-25 precedent that a destructive
migration is reviewed alone rather than riding along with a behaviour change.

## The argument for the shape

The usual justification for an identities table is Google-plus-Apple, which this
product may never have. The better one, which nobody mentions:

**An app transfer between Apple developer teams reissues every user's `sub`.**
Apple provides a `transfer_sub` mapping for exactly this. With the subject
inlined on `User` that migration rewrites the user table under live traffic.
With a join table it inserts rows.

Generalisable: when judging whether a normalisation is premature, look for the
*migration* it makes cheap rather than the *feature* it enables. Features are
speculative. Migrations are not.

## The model

```
Identity
  user                   FK -> User, CASCADE, related_name="identities"
  provider               CharField, choices     # "apple"
  subject                CharField              # the provider's `sub`
  is_private_email       BooleanField, NULLABLE
  real_user_status       IntegerField, NULLABLE
  created_at
  last_authenticated_at  DateTimeField, nullable

  UNIQUE (provider, subject)
```

**Unique on the pair, never on `subject` alone.** A subject is only unique
*within* a provider — each mints opaque strings from its own namespace and
nothing coordinates them. A unique index on `subject` by itself is a
cross-provider collision that fires once, years later, unreproducibly.

**`User.email` does not move.** It is `USERNAME_FIELD`, and `createsuperuser`
plus the whole `/admin/` login path depend on it. Superusers have a password and
no `Identity` at all, which is the sentence that makes the split easy to reason
about: authentication is not something every row must have.

**No `email` column on `Identity`.** Supabase keeps one on both sides and it was
tempting. Nothing would read it until a second provider asserts a different
address, and adding a column nothing reads is what MAC-25 deleted
`is_email_verified` for. Consistency with our own principle beat consistency
with Supabase.

## The two Apple claims

I proposed skipping both. Overruled at the gate, and the call stands on better
reasoning than mine: both are cheap, and both are **unrecoverable later**.
`real_user_status` is sent on the first authorization only, so a user who signs
in before the column exists can never be assessed. That asymmetry decides it,
not whether a reader exists today.

The write rules differ, and the difference is the point:

| Field | Rule | Why |
| -- | -- | -- |
| `is_private_email` | Refreshed on every sign-in | Current state. A user can switch between a relay and their real address |
| `real_user_status` | Written once, never updated | A fact about one moment. Later tokens carry nothing, and writing that would erase a real signal |

Same table, opposite update semantics, because one describes now and the other
describes a moment.

`is_private_email` is three-valued. NULL means Apple did not say, which is not
`False`. Defaulting to `False` would assert a deliverable address nobody told us
about, in the one field whose job is saying whether the address can be trusted.

Both claims are parsed defensively. Apple has emitted `is_private_email` as both
a JSON boolean and a `"true"`/`"false"` string; anything unrecognised becomes
None rather than False. `real_user_status` outside Apple's documented set is
dropped, because a value we cannot interpret survives into the database looking
like a fact. `isinstance(value, bool)` is checked first, since in Python `True`
is an `int` and would otherwise store as status 1, "Unknown".

## The last_login fix, which was three bugs

1. **Nothing wrote it.** simplejwt has an `UPDATE_LAST_LOGIN` setting, but it
   only fires inside `TokenObtainPairSerializer`, and tokens are minted directly
   with `RefreshToken.for_user()`. Turning it on would have changed nothing.
2. **The admin displayed it anyway**, so every active user read as "never logged
   in" — worse than not showing it at all.
3. **It was a field holding a constant**, exactly what MAC-25 deleted
   `is_email_verified` for.

The third is the interesting one. `is_email_verified` was declared, reviewed, and
caught. `last_login` arrived free from `AbstractBaseUser`. **An inherited field
dodges the review a declared one gets.** Nobody chose it, so nobody audited it.
Worth carrying into any base class, model mixin, or framework default.

Fixed by `record_authentication()`, which stamps both sides.
`User.last_login` is person-level and covers a superuser's admin password login;
`Identity.last_authenticated_at` is credential-level. With one provider they move
together. With two, the second answers "which login did they actually use?",
which is the first question support asks.

It calls Django's own `update_last_login` rather than a hand-written save,
because that uses `update_fields` and writes one column instead of the whole row
— which matters when a concurrent request holds a stale user object.

## The migration

`makemigrations` emitted `RemoveField` **before** `CreateModel`, which drops the
data before there is anywhere to put it. The autodetector also cannot write the
copy: nothing tells it that `apple_user_id` and `Identity.subject` mean the same
thing.

Hand-ordered into three steps: `CreateModel`, a reversible `RunPython`, then
`RemoveField`.

Production is empty, so the copy is a no-op there and the reverse was optional.
Both were written anyway and tested through Django's `MigrationExecutor` against
the real historical models — `apple_user_id` exists at 0002 and is gone at 0003,
which is what makes the assertion mean anything. The only honest way to know a
rollback works is to run one, and the cheapest time to learn that is when the
stakes are zero.

The reverse is lossy by nature and says so in its docstring: a user with two
identities cannot round-trip into one column, so it takes the Apple one and
drops the rest. Nobody has two today, which is precisely the window in which
this migration is cheap.

## What broke, and how it announced itself

**`accounts/admin.py`.** `apple_user_id` appeared in `search_fields`,
`list_display`, and the Profile fieldset. I predicted this would fail at page
load; it actually failed at `makemigrations`, because `admin.E108` is a system
check that runs on every management command. Better than predicted, and worth
knowing: the check framework catches `list_display` and `search_fields`
references, so they fail early rather than in front of a user.

The admin now carries an `IdentityInline`, read-only and non-addable — every
field on it is written by the sign-in path from claims Apple signed, and an
editable subject would be a way to hand one person's account to another from a
form whose purpose is support staff looking at accounts they do not own.

`search_fields` reaches through the relation (`identities__subject`), because an
Apple user who hid their address has no email to search on.

`list_display` gained a `provider_list` column, with `prefetch_related` in
`get_queryset`. Without it a page of 100 users is 101 queries — the classic N+1,
and the admin is where it hides best because nobody load-tests it.

**`User.__str__`.** It used to fall back to `apple_user_id`. It now falls back to
the pk rather than reaching for an identity, because querying a relation inside
`__str__` issues one query per row in exactly the view that renders the most of
them.

## Tests

169 in the suite, 25 new across three files.

The one worth reading is the atomicity test. `create_apple_user` writes two rows
inside `transaction.atomic`, and the failure it prevents is silent: a user with
no identity can never sign in, and does not block the retry either, so the next
attempt forks a second account for one person.

It is driven by a **real** constraint violation rather than a mock — two
concurrent sign-ins from one Apple account, where the user INSERT succeeds and
the identity INSERT loses the race. An earlier attempt patched
`Identity.objects.create` and never fired at all, because the manager call goes
through `.using()` and returns a different queryset. The mock tested the mock.

Also covered: two providers sharing a subject, one user holding several
identities, cascade on hard delete and survival on soft delete, both claim-write
rules, the parsing edge cases, and the migration forward, backward, and forward
again.

## Blast radius

- **MAC-27's plan changes.** Resolution keys on `Identity`, not
  `User.apple_user_id`. The four-branch decision table is unaffected. That plan
  gets revised before implementation.
- **MAC-26 is functionally untouched.** Its dataclass is renamed
  `AppleIdentity` → `AppleClaims` and gains the two new fields. The rename was
  free today and would not have been once MAC-27 imported it. `Identity` is the
  row we store; `AppleClaims` is the assertion Apple signed. Calling both
  "identity" was the shape of a naming bug.
- **MAC-29 gets easier.** Purging a user cascades their identities for free.
- No route change, so `pnpm generate:api` is a zero diff.
- Merging deploys to Railway and runs the migration against an empty table.

## Deliberately unhandled

- **Apple ID deletion / revocation webhooks.** Decided at the gate that a
  deleted Apple ID becoming a new account is acceptable. Recorded in doc 04 and
  as MAC-35, which exists to document the decision rather than to schedule work.
- **Unlinking an identity.** No path, no second provider.
- **`transfer_sub` handling.** The table makes it cheap; nothing implements it.
- **Account merging.** One Apple ID is one user.

## For the reviewer

- **The migration ordering**, since getting it wrong loses data and the
  autodetector actively suggests the wrong order.
- **`record_authentication`'s split write rules.** `is_private_email` refreshes,
  `real_user_status` does not. Easy to "simplify" into one rule and silently
  erase Apple's signal.
- **`last_authenticated_at` is currently redundant** with `last_login` while
  there is one provider. Flagged at the gate and kept deliberately.
