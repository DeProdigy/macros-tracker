# MAC-39 — Server-side target guardrails: the two-tier clamp

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
ends. It forbids a 50 kg woman a sensible target and warns a 100 kg man about a
reasonable one. That is the argument for deriving it:

| Person | Suggested calories |
| ------------ | ------------------ |
| 50 kg female | 1,200 to 2,000 |
| 70 kg male | 1,540 to 2,800 |
| 100 kg male | 2,200 to 4,000 |

## Fiber keys on calories, not body weight

Worth its own line because it is the one asymmetry in the module. A 1,400 kcal
day and a 3,000 kcal day genuinely need different fiber, and the guideline is
written per 1,000 kcal. Tying it to weight would miss that.

That is why the suggested range is three functions rather than one returning all
three. `suggested_bounds(profile)` would have to hide the calorie dependency, and
hiding it is how someone later computes fiber against the wrong number.

It also fixes an ordering: `clamp_to_suggested` clamps calories **first**, then
derives fiber's range from the clamped value. A model asking for 6,000 kcal and
110 g of fiber is judged on the 5,000 it actually gets.

## A bug the owner's 5,000 ceiling created

Found while implementing, not while planning.

At 40 kcal/kg the per-kg ceiling passes 5,000 at about **125 kg**. Real people
weigh more than that. Without a `min` against the absolute ceiling, the app would
suggest a number its own write path rejects, and the first person to hit it would
be someone the design never pictured.

So the suggested range is nested inside the absolute range by construction, and
the invariant has a test parameterised across five weights rather than only at
the one that broke.

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

Gates: ruff, ruff format, mypy on 52 files, 301 tests, prettier clean.

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
