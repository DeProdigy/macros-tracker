# MAC-39: server-side target guardrails, the two-tier clamp

Approved 29 Aug 2026. Linear:
[MAC-39](https://linear.app/hintology/issue/MAC-39/server-side-target-guardrails-the-two-tier-clamp).

## Slice and exception

**Slice 1 of 3**, which ends on: *a user can now set their own calorie, protein,
and fiber targets by hand and change them later.*

This ticket has no screen. Under Gate 0 it claims **one** exception: a safety
control landing before the thing it guards. The clamp has to exist before any
endpoint accepts a number.

One exception, not two. The Mifflin-St Jeor baseline used to live here and had
no caller for a whole slice, so it moved to MAC-51, the ticket that calls it. A
ticket naming one rule while quietly carrying a second job is how the exception
list turns into a loophole.

## Files

Two, both new. `apps/api/targets/services.py` and
`apps/api/targets/tests/test_services.py`. No HTTP, no database, no model
provider.

## Two ranges, not one

One range forces a choice between two bad outcomes. Clamp everything and a
person eating 1,400 kcal under medical supervision cannot record it, while the
app silently rewrites their number. Clamp nothing the user typed and someone
sets 400 kcal.

| Range | Applies to | Behaviour |
| --------- | ------------------- | -------------------------------- |
| suggested | model output always | clamped, and the change reported |
| suggested | a user's own number | warned, saved as typed |
| absolute | both | rejected with a 400, never clamped |

The two answer different questions. "Is this a sensible target?" is one a person
may disagree with. "Is this a target at all?" is not.

`clamp_to_suggested` and `reject_outside_absolute` are separate functions rather
than one with a `strict=True` flag. Which caller clamps and which refuses is the
most interesting line of the design, and a boolean argument buries it.

## Pounds, not kilograms

Corrected in review, reversing a decision taken the same day.

The first version took kilograms, on the reasoning that Mifflin-St Jeor is
defined in metric so the client should convert at its edge. Doc 05 said the same.
Both were backwards. It put a conversion in every client for the convenience of
one formula, and it meant the API spoke a unit no screen ever shows.

The formula still needs metric. MAC-51 converts once, where the formula lives.
One conversion in one place beats one in every caller.

The published evidence is per kilogram, so each constant is written as the per-kg
figure divided by `POUNDS_PER_KG` rather than as a pre-computed decimal. A bare
`0.7257` cannot be checked against a paper without reversing it first.

Doc 05, MAC-42, MAC-51, and MAC-41 all carried the old decision and were
corrected with this ticket.

## The numbers, and which ones to trust

The ticket said doc 15's values are a starting point to justify, not copy. Two of
these are well supported. The rest are judgement, and the comments say so.

**Well supported.** Protein at 1.6 to 2.5 g/kg: the 1.6 to 2.2 band for muscle
retention in a deficit is replicated across many trials, and the ceiling is
widened because the evidence says no *added* benefit above 2.2, not that 2.4 is
unwise. Fiber at 10 to 20 g per 1,000 kcal brackets the US Dietary Guidelines
figure of 14.

**Judgement calls.** Calories at 22 to 40 kcal/kg, floored by 1,200 (female) or
1,500 (male). The absolute range of 1,000 to 5,000, which is the owner's.

Doc 15's fixed 1,500 to 3,200 is right for a mid-sized adult and wrong at both
ends. It forbids a 110 lb woman a sensible target and warns a 220 lb man about a
reasonable one. That is the argument for deriving it:

| Person | Suggested calories |
| ------------- | ------------------ |
| 110 lb female | 1,200 to 1,995 |
| 155 lb male | 1,547 to 2,812 |
| 220 lb male | 2,196 to 3,991 |

The untidy numbers are the pound conversion showing through. Rounding the
constants to tidy them would quietly move figures taken from research.

## Fiber keys on calories, not body weight

Worth its own line because it is the one asymmetry in the module. A 1,400 kcal
day and a 3,000 kcal day genuinely need different fiber, and the guideline is
written per 1,000 kcal. Tying it to weight would miss that.

That is why the suggested range is three functions rather than one returning all
three. `suggested_bounds(profile)` would have to hide the calorie dependency, and
hiding it is how someone later computes fiber against the wrong number.

It also fixes an ordering: `clamp_to_suggested` clamps calories **first**, then
derives fiber's range from the clamped value. A model asking for 6,000 kcal is
judged on the 5,000 it actually gets.

## Two crossings, and I only found one

The per-pound ceiling passes 5,000 at about **276 lb**, so the suggested range
would recommend more than the write path allows. I caught that one while
implementing and was pleased with myself in the PR description.

**Review found the mirror image at the other end, and it was worse.**

The floor takes a `max` against a fixed sex number. The ceiling takes a `min`
against a per-pound number. Below about 83 lb for a man and 66 lb for a woman the
two cross, and the range inverts.

An inverted range fails silently in both directions. `clamp` returns the floor
for every input and ignores the ceiling. `contains` returns `False` for every
input. Nothing raises and nothing logs.

The realistic trigger is not a child. It is a typo: 70 instead of 170.

Three fixes rather than one, because the class of bug matters more than the case:

1. `Range.__post_init__` raises on a crossed pair. That covers all six range
   functions at once, not the one that happened to have the bug. It is the same
   argument the docstring already made for naming the fields instead of using a
   tuple: a swapped pair passes every type check, and so does a crossed one
2. `MINIMUM_SUPPORTED_WEIGHT_LB` states the precondition, and MAC-40 enforces it
   so a user gets a 400 rather than a 500
3. A test asserting `floor <= ceiling` across the supported band and both sexes.
   The nesting test does not catch this, because nesting still holds when a range
   inverts

Review also caught that `max(floor, absolute.floor)` on the calorie line could
never fire. It read as defence and was unreachable, which hid that the real
crossing was floor against ceiling. Removed.

And `suggested_fiber_range` did not nest inside its absolute range at all. It
only looked safe because `clamp_to_suggested` clamps calories first. The function
is public, so `suggested_fiber_range(6000)` returned a ceiling of 120 against an
absolute limit of 100. Relying on call order to keep a public function honest is
how the order gets changed by someone who does not know it was load-bearing.

## Rounding direction is not arbitrary

**Floors round up, ceilings round down.** Both tighten the range.

Rounding a floor down would let a value through that the unrounded bound refuses.
The gap is one calorie and the size is silly. The direction is the point, and it
is exactly the kind of thing someone "simplifies" to `round()` while tidying up,
which is why it has a test with a weight that produces real fractions.

## Alternatives rejected

- **One function with `strict=True`.** Fewer names, and it hides the decision at
  every call site.
- **Bounds as plain tuples.** Cheaper, and `bounds[0]` tells a reader nothing.
  Swapping floor and ceiling would pass every type check and every linter.
- **A custom exception class.** `accounts/services.py` already raises DRF's
  `ValidationError` with a code from a pure service, so MAC-40's serializer gets
  its 400 without translating anything.
- **Reporting the first failing field only.** A caller who fixes one, resubmits,
  and is told about the next has been made to guess twice.

## Blast radius

None. New file, nothing imports it. No endpoints, so `openapi.json` does not
move and the drift job has nothing to say.

## Verification

Five mutations, each caught:

| Mutation | Result |
| ---------------------------------------- | ------------------------------ |
| Drop the `min` nesting suggested inside absolute | 4 tests fail |
| Floors and ceilings both `round()` | The rounding test fails |
| Fiber judged on requested, not clamped, calories | The ordering test fails |
| Report only the first failing field | The all-at-once test fails |
| `<=` becomes `<` in `Range.contains` | 4 tests fail |
| Drop the `Range` crossed-bounds guard | 2 tests fail |
| Drop the absolute nesting on suggested fiber | The fiber nesting test fails |
| Guard uses `>=`, so an equal-value range raises | The single-value test fails |

Gates: ruff, ruff format, mypy on 52 files, 319 tests, prettier clean.

**mypy caught a real test bug.** Six assertions read
`assert reject_outside_absolute(...) is None`, which looks like a check and is
one, of a function annotated `-> None`. They asserted nothing. The replacement
calls the function and lets "did not raise" be the assertion, which is what was
meant. Same shape as MAC-38's fake tiebreak test: a passing assertion that
proves nothing is worse than no assertion, because it looks like coverage.

## Deliberately unhandled

- **Mifflin-St Jeor, the activity multiplier, the goal adjustment.** All MAC-51
  in slice 2.
- **Logging an out-of-bounds event.** Belongs with the caller. `ClampResult`
  carries what moved so MAC-41 can log it.
- **Endpoints, persistence, the model call.**

## Open questions

- **Is 2.5 g/kg the right protein ceiling?** Widened from the evidence band to
  cut false warnings. Arguable either way.
- **Should a calorie ceiling exist in the suggested range at all?** Nobody is
  harmed by a high target, and the absolute range already catches typos. Kept
  because the warning is free and a 4,000 kcal goal entered by accident deserves
  a second look.
