# MAC-51: the deterministic proposal

Approved 31 Aug 2026. Linear:
[MAC-51](https://linear.app/hintology/issue/MAC-51/post-apitargetsproposals-the-deterministic-proposal-no-ai).

## Slice and exception

**Slice 2 of 3.** *A user can now answer six questions and have the app work out
their targets.*

Backend only, so it claims the Gate 0 exception for a ticket with no
user-visible face yet. MAC-42 and MAC-43 are the screens, and both consume this.
Building them against a stub would mean the one endpoint they exist to call gets
written last.

## What it is

```
POST /api/targets/proposals/    six answers → three numbers and a paragraph    200
```

200, not 201. Nothing addressable is created. The user accepts a proposal by
posting it to `/api/targets/`, which is what creates a `TargetVersion`.

`proposals` is the resource, not `onboarding`. Settings recomputes proposals when
a weight changes, so naming it after the first caller means renaming it the
moment a second one appears, and by then the name is in the generated client.

**No AI.** MAC-41 was cancelled on 31 Aug 2026. See doc 05.

## The numbers, and where each came from

| Piece | Value | Source |
| -- | -- | -- |
| Resting burn | Mifflin-St Jeor | Published 1990, best general-population accuracy |
| Activity | 1.2 / 1.375 / 1.55 / 1.725 | The conventional multipliers, four levels to match doc 15 |
| Cut | minus 20% | Judgement. A standard moderate deficit |
| Gain | plus 10% | Judgement, and deliberately smaller than the cut |
| Protein | 1.0 g/lb cutting, 0.8 otherwise | 2.2 and 1.76 g/kg, top and middle of MAC-39's band |
| Fiber | 14 g per 1,000 kcal | US Dietary Guidelines, middle of MAC-39's band |

**The cut and the gain are not symmetric, and that is the decision.** A body
builds muscle at a rate it sets; calories past that rate become fat. There is
less to gain from rushing a bulk than from rushing a cut.

**The adjustment is a share of maintenance, not a fixed number of calories.** A
flat 500 kcal deficit is gentle at 250 lb and brutal at 120 lb, because what
matters is the proportion of maintenance removed.

**Fiber keys on the adjusted calories**, not on maintenance and not on weight.
The guideline is written per 1,000 kcal, and a dieting user should get the fiber
for the day they are actually eating.

## Three bugs, all found by running it

The most useful thing in this ticket. None of them is visible by reading the
code, and all three came from putting real people through it before writing a
single test.

### The clamp turned a heavy user's cut into a surplus

A 480 lb man cutting works out at 3,031 kcal against a maintenance of 3,788. The
*suggested* calorie floor is `max(22 kcal/kg, the sex floor)`, and for him the
per-pound term is **4,790**.

So clamping the formula's output to the suggested range raised his deficit into a
1,000 kcal surplus, and handed it to someone who had asked to lose weight.

### The suggested ceiling sits below maintenance for an active user

The mirror image, and it hits an ordinary profile rather than an extreme. 40
kcal/kg is 2,812 for a 155 lb man. A very active one burns 2,864. So "eat roughly
what you burn" was clamped **down**.

**Both are the same mistake in opposite directions.** The per-pound band is a
heuristic for judging a number *a user typed*, which has no formula behind it.
Mifflin already accounts for body size properly, so applying the heuristic on top
does the same job twice and the second pass is worse at it.

`proposal_calorie_range` holds the formula's output to two things: the sex floor,
which is a real safety minimum and correctly catches a small sedentary cutter,
and the absolute ceiling, because suggesting a number the write path would refuse
is a bug whoever it comes from.

**The user-facing warning is untouched.** A heavy person who types 1,400 by hand
is still told it is low. Only our own arithmetic is exempt, and only from the
per-pound half.

### The rationale described a number the clamp had replaced

The first version wrote the sentence from the answers and the number from the
clamp. A user whose calories were raised read:

> 1,200 calories a day. That is 20% below the 1,455 you burn.

1,200 is not 20% below 1,455. **The prose has to describe the number beside it.**

The second version fixed that and assumed the clamp always raises, so a
clamped-down target claimed the answers "worked out lower than that" when they
had worked out higher. The direction is read now, not assumed. Comparing two
numbers costs nothing and cannot be wrong.

## The rationale is a template, and it is assembled from named pieces

Not one format string with holes. The sentences change with the goal: a maintain
plan has no deficit and no weekly rate, and "minus 0% for your goal" is the
sentence that betrays a template written as arithmetic.

Every figure in it is a variable the module already holds, which is the whole
argument against a model writing it. A template reads the real values instead of
being told about them, so it cannot name a number that is not on the screen.

The prose gets its own tests. A numeric assertion never catches "minus 0%".

## The renames

`ai_rationale` becomes `rationale`. The `onboarding_ai` source value becomes
`onboarding`. Both named a producer that will not exist.

**The autodetector proposed drop-and-add for the column**, the same trap MAC-53
hit, and it loses every stored rationale. Hand-written with a `RenameField`, and
a `RunPython` for the source value because `AlterField` alone would leave a
stored `onboarding_ai` string that nothing matches. Data before schema, so no row
is ever left holding a value its own field rejects.

## Validation, and the 500 it prevents

`Profile` documents the 85 to 500 lb band as a **precondition**. Outside it the
suggested floor and ceiling cross and `Range.__post_init__` raises `ValueError`,
which is an unhandled exception and a 500 for an input a user can type.

The serializer bounds it, along with age and height. Those two are data sanity
rather than clinical limits: they stop a typo or a hostile client reaching a
formula that would happily return nonsense.

## The enum collision

`sex` now appears on two request shapes, and drf-spectacular refused to name
them: `SexD67Enum`. `ENUM_NAME_OVERRIDES` points `SexEnum` at
`accounts.models.Sex`, which doc 02 already calls canonical.

**It pins one name. It does not merge the two**, and both the comment and the
first PR body said otherwise. The client still ships `sexEnum.ts` and
`targetProposalRequestSexEnum.ts` with identical members. What the override buys
is that neither name is a hash any more, so an unrelated edit to a choice set
cannot churn the committed client.

Review caught the claim. The next reader takes a comment at its word and goes
looking for one type.

## Files

`targets/services.py`, `targets/serializers.py`, `targets/views.py`,
`targets/urls.py`, `targets/models.py`, `targets/throttles.py` (new),
`targets/migrations/0003_*`, `config/settings/base.py`, and three test files.

The client changes, so `pnpm generate:api` is run and committed.

## Verification

Six mutations, each caught:

| Mutation | Result |
| ------------------------------------------------ | ------------- |
| The proposal uses the full suggested range again | 3 tests fail |
| The female sex constant becomes the male one | 4 tests fail |
| The goal adjustment is a flat 500 kcal | 9 tests fail |
| Fiber keys on maintenance, not adjusted calories | 2 tests fail |
| The rationale ignores the clamp | 2 tests fail |
| The weight precondition leaves the serializer | 2 tests fail |

**The worked Mifflin examples are checked by hand** against the published
equation, not against what the code returns. A test that records current
behaviour cannot tell you the behaviour is wrong.

There is also a sweep across the whole supported weight band, on every
combination of sex, goal and activity, asserting the formula never produces a
target its own absolute range would refuse. If it did, the app would suggest a
number and then reject it when the user accepted.

Gates: ruff, ruff format, mypy on 61 files, 435 python tests,
`makemigrations --check` clean, prettier, `pnpm lint`, `pnpm check-types`,
109 jest tests.

## Deliberately unhandled

- **The six question screens** (MAC-42) and **the result screen** (MAC-43)
- **Persisting the answers.** A user who wants to recompute answers again. Doc 05
  does not say either way, and storing them is a data-retention decision rather
  than a convenience one
- **MAC-50's orange warning.** The bounds it needs now exist behind this
  endpoint, but the client still has no way to ask for them

## Open questions

- **How young a user do we serve?** The age floor is 13, chosen as data sanity.
  Mifflin-St Jeor is fitted for adults and this is a health-adjacent app, so
  whether a minor should get a calorie target at all is a product and App Review
  question the docs do not answer. Easy to raise, and it should be a decision
  rather than a default
- **Protein at 480 g for a 480 lb user.** Inside MAC-39's band, because that band
  is per total body weight. Protein is better keyed to lean mass or goal weight
  for someone carrying a lot of fat, and this is the same shape as the two
  calorie crossings above. Not fixed here because it needs a body-composition
  input nobody collects


---

# Review round two

Three findings. One is a real bug and it is the same shape as bug 3 above, one
macro over.

## Fiber stated a ratio that was false

`suggested_fiber_range(calories)` already followed the clamped calorie figure.
**The value being clamped did not.** It came from `baseline.fiber_g`, computed
from the calories the clamp had just refused.

Two runs on the branch:

- 85 lb woman, 5'0", 25, sedentary, cutting. Calories 1,010 raised to 1,200,
  fiber stays 14. That is 11.7 g per 1,000, and the rationale says 14. The
  guideline figure for 1,200 kcal is 17
- 500 lb man, 6'6", 30, very active, gaining. Calories 6,378 lowered to 5,000,
  fiber stays 89. That is 17.8 per 1,000, against a stated 14

Review swept 40,320 combinations and found a worst deviation of 5.8 g per 1,000.
Protein never clamps anywhere in that sweep, so its sentence was safe.

Fiber is derived from the clamped calories now, then clamped. The unclamped
figure stays in `baseline`, so screen 9f still draws `BASELINE 14 -> SET 17`.

**Why the tests missed it.** `test_fiber_follows_the_calorie_target_not_body_weight`
asserts on `baseline_targets`, never on `propose` output after a clamp. And
`test_the_rationale_does_not_describe_a_number_the_clamp_replaced` checked only
the calorie sentence of the very rationale carrying the wrong fiber claim.

**So the replacement asserts the property rather than the instance.** All three
prose bugs in this ticket were found one at a time, by a person running the
formula and reading the output. `test_every_sentence_in_the_rationale_is_true_of_the_numbers_returned`
sweeps the supported band on every combination and checks that whatever the
clamp does, every figure named in the paragraph is a figure returned beside it.
That is the shared shape all three violated.

## A write-only list that looked like it fed something

`propose` collected `Adjustment` records and nothing read them. `Proposal`
carries `baseline` and derives `clamped` from it, so the list was dead. It read
like something screen 9f consumed.

Replaced with `Range.clamp` directly.

## Two claims that were not true

*"the least this app will suggest for anyone"* is wrong: the floor is 1,500 for
men and 1,200 for women, so a man reads a claim the app contradicts on the next
phone. Two words dropped.

And the `ENUM_NAME_OVERRIDES` comment, above.

## Verification after round two

Three mutations, each caught:

| Mutation | Result |
| --------------------------------------------- | ------------ |
| Fiber is carried over from the baseline again | 3 tests fail |
| Fiber uses the baseline calories for its ratio | 3 tests fail |
| The false "for anyone" claim returns | 1 test fails |

Gates: ruff, ruff format, mypy on 61 files, 439 python tests,
`makemigrations --check` clean, prettier, `pnpm lint`, `pnpm check-types`.


---

# Review round three

One finding, and **the fix in round two caused it.**

## `clamped` was true for users nothing clamped

`propose` recomputed fiber from the rounded integer calories. `baseline_targets`
still computed it from the unrounded `Decimal`. The two land on different
integers whenever the product straddles a rounding boundary.

`Proposal.clamped` compares whole target sets, so a 1 g fiber difference set it
even though no guardrail had fired.

A 20 year old woman, 5'7", 110 lb, sedentary, cutting:

```
baseline = Targets(calories=1250, protein_g=110, fiber_g=17)
targets  = Targets(calories=1250, protein_g=110, fiber_g=18)
clamped  = True
```

Calories and protein identical. Screen 9f would have drawn
`BASELINE 17 -> SET 18` with nothing to explain.

Review swept 9,285,120 combinations and found 29,695 of them, 0.32%, skewed
toward small women cutting. Those are the users the calorie floor already talks
to, so they would have met two confusing messages at once.

Both callers go through `fiber_for(calories: int)` now, which takes the rounded
integer and nothing else. `baseline_targets` rounds calories first and feeds it
the same number. Verified across 39,936 profiles: zero disagreements, zero
spurious clamps.

**The integer is also the honest input.** It is the calorie number on the screen,
and the guideline is a ratio against what the user is told to eat.

## A test that passed by luck

`test_fiber_follows_the_calorie_target_not_body_weight` already asserted:

```python
assert cutting.fiber_g == round(Decimal(cutting.calories) * 14 / 1000)
```

against the rounded integer, while `baseline_targets` computed from the
unrounded Decimal. **32,763 profiles in review's sweep fail that assertion.** It
passed because its single fixture profile is not one of them.

Fourth time this epic a green test proved nothing, after MAC-38's fake tiebreak,
MAC-40's SQL substring, and MAC-50's wrong-premise routing test. The shape here
is new though: the assertion was correct and the sample was not.

## Why the round-two sweep missed it

`test_every_sentence_in_the_rationale_is_true_of_the_numbers_returned` sweeps the
band and still passed, because **every sentence stayed true of the numbers
returned**. The prose was fine. The baseline was wrong.

So the new test asserts a different property: if calories and protein are
untouched, `clamped` is false. Two properties over the same sweep, because one
property only covers what it names.

## Verification after round three

Two mutations, each caught:

| Mutation | Result |
| ----------------------------------------------- | ------------ |
| The baseline rounds fiber from the raw Decimal | 2 tests fail |
| `propose` stops sharing `fiber_for` | 3 tests fail |

Gates: ruff, ruff format, mypy on 61 files, 441 python tests,
`makemigrations --check` clean, prettier, `pnpm lint`, `pnpm check-types`,
109 jest tests, client regenerated with no drift.
