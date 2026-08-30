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

## Pounds, everywhere

Corrected in review, reversing a decision taken the same day.

The first version of this module took a different unit, on the reasoning that
Mifflin-St Jeor is not defined in pounds so the client should convert at its
edge. Doc 05 said the same, because I wrote that too. Both were backwards. It put
a conversion in every client for the convenience of one formula, and it meant the
API spoke a unit no screen ever shows.

MAC-51 owns the one conversion the formula needs, inside the function that needs
it. Nothing here converts, and no constant here is written in anything else.

A second pass removed the last of it. The ratios were computed by a
`_per_pound("1.6")` helper, and every constant comment quoted the source figure
in its published unit. My argument was that the published number is the one a
reader can look up. Review disagreed three times, and by the third it was clear
the citation was costing more than it bought: a reader hitting a unit the module
does not use has to stop and work out whether it matters. It never does. The
constants are literals now and the comments describe what the bounds mean rather
than where the arithmetic came from.

Each literal carries **eight decimal places**, and that number is measured rather
than chosen. Four places move a rounded bound by one at some body weights. Six is
the first that does not. Eight is headroom, checked against the exact value for
every whole pound from 60 to 600, and the 319 tests passing unchanged through the
swap is the second proof.

## The numbers, and which ones to trust

The ticket said doc 15's values are a starting point to justify, not copy. Two of
these are well supported. The rest are judgement, and the comments say so.

**Well supported.** The protein band. Protein for muscle retention in a deficit
is one of the most replicated findings in the field, and the floor sits at the
bottom of that band. The ceiling is widened past it because the evidence says no
*added* benefit higher up, not that higher is unwise. Fiber at 10 to 20 g per
1,000 kcal brackets the US Dietary Guidelines figure of 14.

**Judgement calls.** The calorie ratios, floored by 1,200 (female) or 1,500
(male). The absolute range of 1,000 to 5,000, which is the owner's.

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

- **Is the protein ceiling too generous?** Widened past the evidence band to
  cut false warnings. Arguable either way.
- **Should a calorie ceiling exist in the suggested range at all?** Nobody is
  harmed by a high target, and the absolute range already catches typos. Kept
  because the warning is free and a 4,000 kcal goal entered by accident deserves
  a second look.
