# MAC-73: Photo analysis rejects zero-calorie items like diet soda

Linear:
[MAC-73](https://linear.app/hintology/issue/MAC-73/photo-analysis-rejects-zero-calorie-items-like-diet-soda).

## Problem

A photo of a Sunkist Zero returns 502. The screen shows "Could not analyze this
photo."

Alex found this on a physical iPhone on 16 Sep 2026, right after MAC-71 and MAC-72
made the photo flow work end to end.

## Evidence

Five device attempts gave 502, 201, 502, 201, 201. The two failures both returned a
69-byte body, which is `food_analysis_invalid_output` from `ai/views.py:66`. That
branch means OpenAI returned items and the local serializer threw them out.

The failing photo was a zero-calorie drink. The three successes were real food.

The 69-byte body is what separated this from MAC-72. A provider failure returns 72
bytes from a different branch. Counting the bytes told us the failure had moved.

## Root cause

`FoodAnalysisResultSerializer.validate_items` in `apps/api/ai/serializers.py`:

```python
if not any(
    item[field] > 0 for item in value for field in ("calories", "protein_g", "fiber_g")
):
    raise serializers.ValidationError("Return at least one positive macro value.")
```

A Sunkist Zero is 0 calories, 0 protein, 0 fiber. Every macro is zero, `any()` is
false, and a correct answer becomes a 502.

The rule was meant to catch a hallucinated empty result. It cannot. An all-zero
response about a diet soda and an all-zero response about a blank wall are the same
three numbers. The check inferred model quality from data that does not carry that
signal.

Everything with no calories hit this: diet soda, black coffee, plain tea, water,
sugar-free gum.

## Files touched

- `apps/api/ai/serializers.py`
- `apps/api/ai/tests/test_serializers.py`
- `plans/tickets/MAC-73.md`

## Approach

Delete the positive-macro rule. Keep the non-empty rule, which tests something the
data can answer.

The human is already the filter. MAC-54 shows every item before the user saves, and
MAC-57 shipped per-item editing. A useless result costs one tap to discard. A
rejected real result costs the user the feature.

A docstring records why the check was removed, so nobody re-adds it as a guard
against hallucination.

## Regression test

Two tests in `test_serializers.py`. One validates a result where every macro is
zero. One asserts an empty item list still fails.

No test covered `validate_items` before this. The positive-macro branch was never
exercised, which is how it survived two tickets and reached a device.

Confirmed red then green. The failure message on the old code is the exact string
the device hit: "Return at least one positive macro value."

## Verification

1. The zero-macro test fails on the old serializer, then passes. Done.
2. `pnpm pre-pr` passes.
3. On the iPhone: a photo of a zero-calorie drink returns items instead of an error.

## Alternatives rejected

- **Give the model a `no_food_visible` boolean** and branch on that instead of on
  the numbers. This is the correct long-term design, because it asks the model the
  question rather than inferring the answer. It changes the provider schema, the
  prompt, and the service, so it is its own ticket.
- **Reject only when every item is zero and there is exactly one item.** A guess
  dressed as a rule. A single black coffee is exactly that shape.
- **Return 200 with an empty list.** The endpoint creates an analysis resource, so
  an empty success would push the client into inventing its own error state.

## Concepts in play

- **A validator must test what the data can answer.** "Is this list empty" is such a
  question. "Did the model do a good job" is not.
- **Prefer a signal over an inference.** To know whether the model saw food, add a
  field where it says so.
- **An untested branch is an unwritten assumption.** Nothing ever reached this one,
  so nothing challenged it.
- **Response byte counts are evidence.** Two error branches with different copy
  produce different content lengths, and the access log records both.

## Horizontal ticket

A bug fix, not a slice. A user can now photograph a zero-calorie drink and log it.

## Blast radius

One `if` block in one serializer. No API change, no client regeneration, no
migration, no mobile change. The 502 contract is unchanged and still fires for a
genuinely empty list.

## Deliberately unhandled

- **The generic mobile copy.** `photo.tsx` maps every non-429 failure to one message
  and ignores the `detail` the API sends. Worth its own ticket.
- **The `no_food_visible` field.** See alternatives.
- **Any replacement guard against a useless answer.** Removed on purpose. The user
  reviews the items.

## Open questions

None.
