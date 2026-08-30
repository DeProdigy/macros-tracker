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
means MAC-28's reasoning was right and only its unit was wrong. Bounds become
85 to 500 lb, shared with the current weight. See below for why not a straight
conversion of the old 20 to 400 kg.

**`current_weight_lb` is new.** 85 to 500 lb, the same band as the goal weight.

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

## The band is a precondition, and I only guarded one end

Below 85 lb the suggested calorie floor passes the ceiling and the range inverts.
MAC-39 documented that on `Profile` and left enforcement to whoever wrote the
endpoint. Putting the validator on the column is better than on the endpoint: it
covers the admin and any future writer, and it turns a bad weight into a 400 at
the edge rather than a 500 from the range guard.

**The first version paired it with a 1000 lb ceiling, picked as "catches a typo"
without checking the top.** Review found it. The range inverts at both ends: the
ceiling stops at 5,000 kcal while the floor keeps climbing, so they cross again
at 501.05 lb.

```
440 lb  Range(floor=4391, ceiling=5000)
500 lb  Range(floor=4990, ceiling=5000)
502 lb  ValueError: Range floor 5010 is above ceiling 5000.
```

`PATCH /api/users/me/ {"current_weight_lb": "600.00"}` was accepted and then
crashed, which is the exact failure the floor was added to prevent. A 600 lb
person is real, and 1000 is also what a mistyped 100.0 looks like.

`MAXIMUM_SUPPORTED_WEIGHT_LB` mirrors the min, the validator drops to 500, and a
second test pins it. Worth naming the shape rather than the instance: **a bound
that clamps against a constant while its opposite scales freely will cross
somewhere.** I checked one end and stopped, twice now.

## One band for both weights

`goal_weight_lb` and `current_weight_lb` measure the same thing in the same unit.
The first version had 44 to 880 on one and 85 to 1000 on the other, so a goal of
44 lb passed while a current weight of 44 lb failed.

Nobody had picked 44 or 880 in pounds. They were 20 and 400 kg carried across, and
carried wrong: 400 kg is 881.85 lb, so a stored maximum would have converted to a
value its own validator then rejected.

Both share `WEIGHT_FLOOR_LB` and `WEIGHT_CEILING_LB` now.

**Tightening the ceiling to 500 made that gap wider, not narrower**, which review
caught after I had written a comment claiming the opposite. The old column
allowed 20 to 400 kg; the new one allows 38.56 to 226.80 kg in disguise. Neither
end nests:

```
 20 kg ->  44.09 lb   below 85
400 kg -> 881.85 lb   above 500
```

Validators do not run on a `RunPython` save, so the migration would have written
those rows regardless and left them unsavable. `refuse_unconvertible_rows` stops
before the conversion and raises, naming the rows.

Raising rather than clamping. Clamping silently changes a number a person
entered, and avoiding exactly that is why the migration was hand-written. Raising
makes a deploy stop and someone look, which is the right amount of noise for a row
nobody expected. Against an empty table it does nothing.

## Two values written twice, and the tests that make that safe

`accounts` owns the column. `targets.services` owns the arithmetic. Neither can
import the other: `targets` holds a foreign key to `accounts`, so an import back
would invert the app order doc 02 sets out and reorder the migrations.

So `Sex` and both ends of the weight band exist in both places.
`targets/tests/test_units.py` asserts they agree, in four tests:

- the two `Sex` enums hold the same values
- every stored sex has a calorie floor behind it, which is the sharper version:
  a value could exist in both enums and still be a `KeyError` inside a range
  function
- the model's weight floor matches `MINIMUM_SUPPORTED_WEIGHT_LB`
- the model's weight ceiling matches `MAXIMUM_SUPPORTED_WEIGHT_LB`, which is the
  one review had to add because I pinned only the floor

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

Five mutations, each caught:

| Mutation | Result |
| ------------------------------------------- | ------------------------ |
| Model weight floor drops from 85 to 50 | The floor-match test fails |
| A third `Sex` value with no calorie floor | Two tests fail |
| The migration's `*` becomes `/` | Two migration tests fail |
| The `RunPython` line is deleted | The conversion test fails |
| The refusal guard is removed | The out-of-bounds test fails |

Gates: ruff, ruff format, mypy on 53 files, 334 tests, `makemigrations --check`
clean, prettier, `pnpm lint`, `pnpm check-types`, `pnpm test`.

## Deliberately unhandled

- **A weight history.** This stores the latest value. When the log arrives,
  `current_weight_lb` becomes a denormalized copy of the newest row and needs the
  same argument doc 02 gives the daily totals.
- **Writing the fields.** MAC-42 sends the answers and MAC-51 persists them.
- **The Settings screen** that will let someone change their weight later.

## `sex` clears with `""`, not `null`, and that is a toolchain compromise

Every other clearable field on `UserSettingsSerializer` takes `null`. `sex` is a
blank-string column and takes `""`. Review asked for `allow_null` with a
coercion, to match.

It does not survive generation. `allow_null` on a blank-capable `ChoiceField`
makes drf-spectacular emit `nullable: true` **and** a `NullEnum` member of the
same `oneOf`, and orval refuses it: `Duplicate schema names detected: 2x
PatchedUserSettingsRequestSex`. The client stops building entirely, which is a
worse failure than the papercut it fixes.

So the difference is documented in the field's `help_text`, which reaches the
OpenAPI schema and the generated client rather than living only in a comment. A
test pins both halves, so nobody "fixes" the asymmetry without rediscovering the
cost.

## The read type said `sex` could never be blank

`User.sex` reads back as `""` for anyone who has not answered, and the generated
client typed it `SexEnum` with no blank member. The committed `openapi.json`
disagreed with itself: the sign-in example showed `"sex": ""`, a value its own
`User` schema forbade.

What that breaks is quiet. A client switches on `user.sex` with no default,
TypeScript believes the switch is exhaustive, and every unanswered user falls
through it with nothing raised.

Fixed by declaring the field explicitly on `UserSerializer` rather than letting
`ModelSerializer` infer it. `UserSex` is now `SexEnum` merged with `BlankEnum`.

## Open questions

- **Should `current_weight_lb` be required before a target can be written?**
  Today it is nullable and MAC-40 has to decide what to do with a null. Refusing
  the write is defensible and so is skipping only the protein bound. It belongs
  in MAC-40's plan, where the endpoint exists to have the behaviour.
