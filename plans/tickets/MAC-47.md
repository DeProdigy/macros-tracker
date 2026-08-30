# MAC-47: nothing ever set onboarding_completed

Approved 30 Aug 2026, then rescoped the same day. Linear:
[MAC-47](https://linear.app/hintology/issue/MAC-47/nothing-ever-sets-onboarding-completed-so-the-launch-gate-loops).

## Rescoped mid-PR: onboarding is a hard gate

This ticket shipped an `onboarding_skipped_at` column to make the skip work
properly. The owner read it and asked why the skip existed at all.

I checked the docs before answering, and they backed the skip: doc 05 said "the
first meal comes before the questions" and "onboarding can be skipped or
abandoned", doc 26 drew a *Not now* exit. Those docs were stale rather than
right. The owner ruled the questions come first, the first meal comes after, and
there is no skip.

**What still ships is the actual bug.** Nothing ever wrote `onboarding_completed`.
That is worse under a hard gate, not better.

**What is deleted:** the column, its migration, both serializer halves, the
clock-skew validator, and the placeholder's *Not now*.

**What was added instead:** the route guard. See below.

The sections after this one describe the two-field design and are kept as
history. They are wrong about the product now.

## Slice and exception

**Slice 1 of 3**, which ends on: *a user can now set their own calorie, protein,
and fiber targets by hand and change them later.*

It changes a screen, so it claims no Gate 0 exception.

## The bug

`User.onboarding_completed` was read in two places and written in none.

`apps/mobile/app/index.tsx` routed on it. `app/(auth)/login.tsx` did the same
after sign-in. `PATCH /api/users/me/` refused it on purpose, and a test asserted
that refusal. The model defaulted it to `False`.

So nothing in the repo could turn it true. A user set targets, closed the app,
and reopened it in onboarding. Forever.

The bug is invisible in every ticket taken alone. It shows up only if you ask
who writes the field, which no ticket did.

## Two fields, because two different things happened

| Field | Writer | Why |
| -- | -- | -- |
| `onboarding_completed` | server, on the first `TargetVersion` | a fact about the data |
| `onboarding_skipped_at` | client, via `PATCH /api/users/me/` | a choice only the client knows |

The gate routes to Today when **either** is set.

That difference in writability is the interesting part, and it is not an
inconsistency. `onboarding_completed` is derived, so a client asserting it is a
client lying. A skip is a decision the server has nothing to derive from, and
the worst a malicious client achieves by recording one is skipping a screen that
has a skip button on it.

Overloading one boolean to mean "completed or skipped" was the alternative. The
name would lie, and E5's re-prompt row needs to tell the two apart.

A nullable timestamp rather than a second boolean. "When" costs nothing to store
and answers a question a boolean cannot.

## The reading that was rejected

**A. "This user has targets."** Set the flag when the first `TargetVersion`
exists, and derive everything. Tidier.

It breaks the exit. Doc 26 makes *Not now* a supported end state, and under A a
skipper gets thrown into the onboarding stack on every cold start.

**B. "This user has been through the flow, whatever they chose."** Shipped.

Worth naming the shape, because it recurs: **a boolean meaning "the user
resolved this" is not the same as one meaning "the data exists", and picking the
second because it is derivable is how a supported choice becomes a nag.**

## One door, in services.py

`services.create_version` is now the only function that makes a `TargetVersion`.
MAC-40's endpoint calls it today. MAC-45's backfill and MAC-51's accepted
proposal call it next.

A second creation path is a second place to forget the flag, and this ticket
exists because the flag had no writer anywhere.

**Not a signal.** A `post_save` receiver also fires from fixtures, from
migrations, and from any test that builds a row, and no reader of the call site
knows it happened. The cost is paid by whoever debugs it later.

It sits in `targets/services.py`, which until now said "no database" in its own
docstring. That claim is now scoped to the half above the `--- the write path
---` line, and the docstring says so. The clamp stays pure arithmetic.

## The condition is "not done yet", not "this is the first version"

```python
User.objects.filter(pk=user.pk, onboarding_completed=False).update(onboarding_completed=True)
```

One conditional UPDATE, which buys three things a `count() == 0` check does not.
No extra query. Two racing requests cannot both decide they are first, because
the database resolves the condition rather than Python. And a second version
matches zero rows, which is the behaviour the ticket asks for.

It is not identical to "first version". An operator who clears the flag by hand
gets it back on that user's next target. That is the wanted answer, and it falls
out of writing the condition in terms of the fact instead of the count.

Both writes are in one transaction. A target that saves while the flag fails
leaves a user who owns targets and is still told to go and set some.

## The mutation that survived, and the test it forced

**"Drop `onboarding_completed=False` from the filter" passed every test.**

The endpoint test asserting the flag is still true after a second target passes
either way, because writing True over True is invisible from outside. So the
design above was documented at length and proved by nothing.

The first replacement test counted queries and asserted no UPDATE ran. It
failed, and it was wrong: the statement still runs on a later target, it simply
matches no rows. The condition lives in the WHERE clause.

`test_the_flag_update_carries_its_condition_in_the_where_clause` asserts on the
SQL instead. White-box on purpose, because what the condition buys is that the
**database** decides who is first. Move the check into an `if` in Python and two
racing requests both read False, both write, and the guarantee is gone with
every test still green.

## Who stamps the skip time

The client sends it, and the server checks the clock is within a day.
`MAX_CLIENT_CLOCK_SKEW` mirrors `targets/serializers.py`'s
`MAX_CLIENT_DATE_SKEW`, one ticket old.

The alternative was accepting any value and overwriting it with
`timezone.now()`. That makes a writable field quietly ignore what it was sent,
and a reader of the schema has no way to know.

A phone a few hours out, or one that queued the write offline, is a real user
and passes. A year out is a bug or a client inventing history, and the field
exists to answer how long ago the skip happened.

## The placeholder's Not now, and the error it swallows

`app/onboarding.tsx` is a placeholder MAC-42 deletes in slice 2. It still gets
the write, because in slice 1 this button is the only route a new user has to
Today, and therefore the only route to the Settings row where targets get set.

**A failed write is swallowed and the user still leaves.** The exit is a promise
doc 26 makes. Blocking it on a network call traps a user with no signal on the
one screen whose point is that you can leave it. The cost of failing is that the
skip lasts one launch, which is exactly where the screen was before this ticket.

No error message either, because there is no action to offer. Tapping again is
what a returning user does anyway.

## One helper, two call sites

`lib/onboarding.ts` owns `needsOnboarding(user)`. `index.tsx` and `login.tsx`
both call it.

A two-part condition duplicated across two files is a bug waiting for the day
someone changes one of them. Both files had the one-part version inline, and
both were wrong in the same way.

`session.updateUser` is new, and separate from `signIn` which takes the same
argument and does nearly the same thing. Calling `signIn` from a settings screen
would read as signing someone in. It ignores the write when the session is not
signed in, because a PATCH response can land after the global 401 handler has
already signed the user out.

## Files

Backend: `accounts/models.py`, `accounts/migrations/0007_user_onboarding_skipped_at.py`,
`accounts/serializers.py`, `accounts/views.py`, `targets/services.py`,
`targets/serializers.py`.

Mobile: `lib/onboarding.ts` (new), `lib/session.tsx`, `app/index.tsx`,
`app/(auth)/login.tsx`, `app/onboarding.tsx`.

The migration is a plain `AddField`, autogenerated and left alone. Nothing like
MAC-53's hand-written one, because nothing moves.

## Blast radius

`User` gains a column, so `openapi.json` and the generated client both move.
`pnpm generate:api` run and committed.

Two routing screens change behaviour. Every signed-in user with
`onboarding_completed = False` and no skip still lands on onboarding, which is
what they get today.

**The view docstrings were the drift risk again.** drf-spectacular pulls them
into the schema, and `getCurrentUser` described routing on one field. Fixed
before the final regeneration, which is the lesson MAC-40 paid for.

## Verification

Eight mutations, each caught:

| Mutation | Result |
| -------------------------------------------- | ------------------------- |
| The gate reads `onboarding_completed` alone | 2 mobile tests fail |
| `create_version` does not flip the flag | 5 tests fail |
| The flip is unconditional | 1 test fails |
| The two writes are not in one transaction | 1 test fails |
| *Not now* routes without updating the session | 1 mobile test fails |
| The in-memory user is left stale | 2 tests fail |
| The clock-skew check is removed | 2 tests fail |
| `onboarding_skipped_at` drops out of the write shape | 6 tests fail |

Gates: ruff, ruff format, mypy on 58 files, 370 python tests,
`makemigrations --check` clean, prettier, `pnpm lint`, `pnpm check-types`,
91 jest tests.

## Deliberately unhandled

- **MAC-46's designed bridge screen.** This ships the column, the endpoint, the
  gate, and the placeholder's write
- **MAC-45's entry backfill.** It comes through the same `create_version` door
- **E5's dismissible re-prompt row on Today.** It is what the timestamp is for
- **The `Sex` mirror in `targets/services.py`.** That module now imports its own
  model, so importing `accounts.models.Sex` would cost nothing. MAC-53 chose the
  mirror deliberately and `test_units.py` pins the copies together. Changing it
  is fair and it is not this ticket

## Open questions

- **Should Settings show anything to a user who skipped?** MAC-44 puts targets
  in Settings and this ticket makes the skip stick. Whether the row nudges a
  skipper, and how loudly, is a design question doc 26 does not answer


---

# The rescope, 30 Aug 2026

Everything above describes the two-field design. This is what actually shipped.

## One field, and it is server-derived

`onboarding_completed` turns true when the user's first `TargetVersion` is
written. No client can set it. There is no second field, because there is no
second way to leave.

`services.create_version` is unchanged and so is every argument for it. The
conditional UPDATE, the single transaction, the one-door rule, and the SQL
assertion that pins the WHERE clause all survive the reversal untouched. Only
the skip half went.

## The hole the audit found

The task said to cross-reference the code and make sure onboarding is really a
blocker. It was not.

`apps/mobile/app/(app)/_layout.tsx` guarded authentication and not onboarding.
The launch gate at `/` checked it, and **a deep link straight to `/today` never
runs the launch gate.** So a user with no targets walked in.

That was tolerable while the skip existed, because leaving was allowed anyway. It
is not tolerable now. **A gate with a way round it is not a gate.**

The check went into the route guard rather than into each screen, by the same
argument that file already made for auth: a per-screen check is the one that gets
forgotten exactly once, by a screen written months from now that never thought
about onboarding.

`needsOnboarding` now has three callers and reads one field. A one-line helper
looks like over-abstraction until you notice the rule changed twice in a day.

**The server side is still open, and it is worth naming.** The mobile guard stops
a person, not a request. Doc 02 now says `DailyLog.target_version` is NOT NULL,
so whatever builds entry creation in E4 must refuse a user with no current
version, or a bad request becomes a 500 instead of a 400.

## What a sequencing decision reached

The reversal deleted more than a screen, which is the interesting part.

- `onboarding_skipped_at`, the column and everything around it
- `9d`, the bridge screen, and MAC-46 with it
- the nullable `DailyLog.target_version`, its backfill, and MAC-45
- the "macros without progress" render state on the dashboard, doc 07
- the dismissible re-prompt row on Today, parked for E5
- doc 06's warning about the camera prompt arriving four seconds after install,
  which the new order fixes for free

Each of those was defensible on its own. None of them was needed. **A decision
about what order two screens come in set a column's nullability, a dashboard
render state, and two tickets**, and a reversal that only changed the routing
would have left all of it standing.

## The cost, accepted rather than worked around

The placeholder is now a dead end. Until MAC-50 lands, a new user cannot reach
the app at all.

I considered leaving a temporary escape on the placeholder that wrote nothing.
Rejected: a hidden bypass on a gate is worse than a dead end, and the dead end is
honest about the state of the work. MAC-50 is raised to Urgent and rescoped to be
reachable from onboarding, which makes it the way *through* the gate.

## Docs and tickets updated

Docs 02, 05, 06, 07, 21, 26 and the Decision Log, edited in Linear and mirrored
with `pnpm sync:plans`. MAC-45 and MAC-46 cancelled. MAC-42, MAC-47 and MAC-50
rescoped.

## Verification after the rescope

Five mutations, each caught:

| Mutation | Result |
| ------------------------------------------ | ------------------- |
| The route guard drops the onboarding check | 1 mobile test fails |
| `needsOnboarding` always returns false | 4 mobile tests fail |
| `create_version` does not flip the flag | 6 tests fail |
| The flip is unconditional | 1 test fails |
| The two writes are not in one transaction | 1 test fails |

Gates: ruff, ruff format, mypy on 58 files, 364 python tests,
`makemigrations --check` clean, prettier, `pnpm lint`, `pnpm check-types`,
90 jest tests.
