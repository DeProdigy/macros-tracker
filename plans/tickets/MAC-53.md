# MAC-53: pounds on User, and the two onboarding answers worth keeping

Approved 30 Aug 2026. Linear:
[MAC-53](https://linear.app/hintology/issue/MAC-53/usergoal-weight-kg-stores-kilograms-in-a-pounds-app).

## Slice and exception

**Slice 1 of 3**, which ends on: *a user can now set their own calorie, protein,
and fiber targets by hand and change them later.*

No screen, and it claims the Gate 0 exception for foundational work with no
user-visible face. MAC-40 is blocked on it: the create endpoint has nothing to
bound a protein target against until these columns exist.

## What this fixes, and how it was found

MAC-40's plan stalled on a question nobody had asked yet. `reject_outside_absolute`
needs a `Profile`, which is sex plus weight, and the server had neither.

I first proposed flattening the protein bound so no profile was needed. The owner
pushed back with the obvious question: **the app already asks for weight.**

It does. Question 4 of the six. It was being asked, used for one calculation, and
thrown away. Meanwhile `goal_weight_kg` was persisted, so the app stored the
target and forgot the number it is measured against.

That is backwards, and flattening the bound would have papered over it.

## Three changes

**`goal_weight_kg` becomes `goal_weight_lb`.** It shipped in MAC-28, before the
US units decision. Every screen that will ever write it shows pounds, so the
column was one call site away from receiving them under a name that said
otherwise. That is the exact failure the unit suffix exists to prevent, which
means MAC-28's reasoning was right and only its unit was wrong. Bounds move from
20-400 kg to 44-880 lb.

**`current_weight_lb` is new.** 85 to 1000 lb.

**`sex` is new.** `blank` with a `""` default rather than nullable, matching
`name` and `dietary_constraints` and ruff's DJ001. A nullable `CharField` gives
two ways to spell "empty". The two weights stay genuinely nullable, because 0 lb
is a value rather than an absence.

## The migration the autodetector got wrong

`makemigrations` proposed `RemoveField` plus `AddField` for the rename, because
it cannot tell a rename from a coincidence of shape. That drops every stored goal
weight.

There are no rows today, so it would have been silently harmless. **That is what
makes it worth not shipping**: the migration would have read as correct right up
until the first user had a goal.

Replaced by hand with a `RenameField`, a `RunPython` conversion, and an
`AlterField` for the new bounds. The reverse is a real inverse rather than a
`noop`, because a migration that cannot go back is one you find out about while
trying to go back.

## 85 lb is a precondition, not a sanity bound

Below it the suggested calorie floor passes the ceiling and the range inverts.
MAC-39 documented that on `Profile` and left enforcement to whoever wrote the
endpoint.

Putting the validator on the column is better than putting it on the endpoint. It
covers the admin and any future writer for free, and it is what turns a bad
weight into a 400 at the edge rather than a 500 from the range guard.

## Two values written twice, and the tests that make that safe

`accounts` owns the column. `targets.services` owns the arithmetic. Neither can
import the other: `targets` holds a foreign key to `accounts`, so an import back
would invert the app order doc 02 sets out and reorder the migrations.

So `Sex` and the 85 lb floor exist in both places. `targets/tests/test_units.py`
asserts they agree, in three tests:

- the two `Sex` enums hold the same values
- every stored sex has a calorie floor behind it, which is the sharper version:
  a value could exist in both enums and still be a `KeyError` inside a range
  function
- the model's weight validator matches `MINIMUM_SUPPORTED_WEIGHT_LB`

Duplication is a real cost and this is the honest version of it. The tests are
what make it safe rather than a bug waiting for whoever edits one side.

## Target weight, since it was asked about

`goal_weight_lb` is stored and **nothing computes from it**. Mifflin-St Jeor does
not read it. The clamp does not read it. Doc 05 moved it out of onboarding
precisely because it improves target quality without blocking anything.

It earns its place as context for the model, where rate-of-loss guidance in the
rationale can use it. That is slice 3.

Worth stating plainly rather than leaving a column that looks load-bearing and
is not.

## Alternatives rejected

- **Flatten the absolute protein range.** My first proposal. It removes the need
  for a weight by making the bound less precise, and it leaves the app still
  discarding an answer it asked for. Fixing the storage is the smaller change in
  the end.
- **Send `weight_lb` with every target write.** Works from onboarding, where the
  client has it. Fails from Settings, where nobody asked for a weight and the
  screen would have to invent a field to satisfy a server-side guard.
- **A separate weight-log table now.** The right shape eventually, and E5 and E11
  will both want it. Today it is a column nothing reads, and building the history
  before the single value has a caller is speculative.

## Blast radius

`User` gains two columns and renames one, so the generated client changes and the
drift job has something to say for the first time this epic. `pnpm generate:api`
run and committed.

Nothing reads the new fields yet. MAC-40 is the first, and MAC-42 is what starts
writing them.

## Verification

Two mutations on the drift guards, each caught:

| Mutation | Result |
| ------------------------------------------- | ------------------------ |
| Model weight floor drops from 85 to 50 | The floor-match test fails |
| A third `Sex` value with no calorie floor | Two tests fail |

Gates: ruff, ruff format, mypy on 53 files, 322 tests, `makemigrations --check`
clean, prettier, `pnpm lint`, `pnpm check-types`, `pnpm test`.

## Deliberately unhandled

- **A weight history.** This stores the latest value. When the log arrives,
  `current_weight_lb` becomes a denormalized copy of the newest row and needs the
  same argument doc 02 gives the daily totals.
- **Writing the fields.** MAC-42 sends the answers and MAC-51 persists them.
- **The Settings screen** that will let someone change their weight later.

## Open questions

- **Should `current_weight_lb` be required before a target can be written?**
  Today it is nullable and MAC-40 has to decide what to do with a null. Refusing
  the write is defensible and so is skipping only the protein bound. It belongs
  in MAC-40's plan, where the endpoint exists to have the behaviour.
