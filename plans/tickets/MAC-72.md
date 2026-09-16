# MAC-72: Fix food analysis: Decimal fields break OpenAI structured output

Linear:
[MAC-72](https://linear.app/hintology/issue/MAC-72/fix-food-analysis-decimal-fields-break-openai-structured-output).

## Problem

Photo analysis fails on a physical iPhone. `POST /api/analyses/` returns 502 with
`ai.provider.ProviderOutputError`. The screen shows "Could not analyze this photo."

MAC-71 fixed the R2 upload, which exposed this. Every iOS build before that failed
earlier, so this call was never made from a device.

## Evidence

Railway logs, 16 Sep 2026 03:13 UTC:

```
File "/app/ai/provider.py", line 78, in analyze_food
  raise ProviderOutputError(
ai.provider.ProviderOutputError
"POST /api/analyses/ HTTP/1.1" 502
```

`analyze_food` raises when `response.output_parsed` is None. A local reproduction
against the real OpenAI API gives:

```
status: incomplete
incomplete_details: IncompleteDetails(reason='max_output_tokens')
usage: input_tokens=0, output_tokens=0
output: []
```

## Root cause

`ProviderFoodItem` typed `calories`, `protein_g`, and `fiber_g` as `Decimal`.
Pydantic renders a `Decimal` field as a union:

```json
"anyOf": [
  {"type": "number", "minimum": 0.0},
  {"type": "string", "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"}
]
```

The request goes out with `"strict": true`. In strict mode OpenAI compiles the
schema into a decoder grammar before it generates a token. It cannot compile that
shape, so generation never starts.

The reported reason is misleading. It says `max_output_tokens`, but usage is zero
in and zero out. Raising the budget from 4096 to 16000 changes nothing.

The pattern also carries a negative lookahead, `(?!^[-+.]*$)`. Constrained decoders
usually run RE2-style engines, which have no lookahead. So the lookahead may be the
exact trigger rather than the union. The two were not separated, because the fix
removes both and each separation test costs a paid API call.

## Proof, same model and prompt and photo

| Schema field type | Result |
| -- | -- |
| `Decimal` | incomplete, 0 tokens, no items |
| `float` | completed, 24 items, 905 in / 916 out |

The `float` run keeps every `Field` constraint: `min_length`, `max_length`, and
`ge=0`. So the constraints are not the problem.

## Files touched

- `apps/api/ai/provider.py`
- `apps/api/ai/tests/test_analysis_service.py`
- `plans/tickets/MAC-72.md`

## Approach

Type the three macro fields as `float`. Drop the now unused `Decimal` import.

Nothing downstream changes. `_rounded_macro` in `apps/api/ai/services.py:218`
already does `Decimal(str(value))`, and `str()` on a Python float returns the
shortest string that round-trips. The serializer and the database still store
strings rounded to two places.

A class docstring on `ProviderFoodItem` records why the type is `float`, because
the next person to read it will want to "fix" it back to `Decimal`.

## Regression test

`test_provider_schema_declares_one_type_per_field` walks the generated schema and
collects any property that declares `anyOf` or `oneOf`. It asserts the list is
empty.

The first version of this test searched the serialised schema for the string
`anyOf`. It failed against the fixed code, because pydantic copies a class
docstring into `description`, and the new docstring explains the word. Walking the
property definitions tests the structure instead of the prose.

Confirmed red then green. On the old code the failure names
`ProviderFoodItem.calories` and the two other macros. On the new code all 31 `ai`
tests pass.

This test cannot prove OpenAI accepts the schema, because it never calls OpenAI.
The device run is the only proof of that, and each run costs money.

## Verification

1. The new test fails on the old provider, then passes. Done.
2. `pnpm pre-pr` passes.
3. On the iPhone: a photo returns items, and Railway logs show `POST /api/analyses/`
   with 201.

## Alternatives rejected

- **Keep `Decimal`, override the schema** with
  `Annotated[Decimal, WithJsonSchema({"type": "number"})]`. It works and keeps the
  exact type. It also sets a trap: the annotation must be repeated on every new
  numeric field, and a missed one fails at runtime against a paid API.
- **Type the fields as `str`.** Precision would be exact. It also invites the model
  to answer "about 12" and moves every parse error into `_rounded_macro`.
- **Raise `max_output_tokens`.** Tested at 16000. No change, because the token
  budget was never the cause.

## Concepts in play

- **A provider schema is a wire format, not a domain model.** One describes what a
  third party must generate. The other describes what this app stores. Sharing one
  type across that line ties your storage precision to a vendor's JSON schema
  support.
- **A vendor error names the symptom it noticed.** `max_output_tokens` with zero
  tokens used is a contradiction, and the contradiction is the signal.
- **Structured output is a constrained decoder.** The provider turns the schema into
  a grammar first. An unsupported construct fails at compile time, which is why
  usage is zero and the output list is empty.
- **Assert on structure, not on serialised text.** A string search over a JSON dump
  matches documentation as readily as data.

## Horizontal ticket

A bug fix, not a slice. A user can now photograph food and receive itemized
estimates.

## Blast radius

Three type annotations and one import in one module. No API change, no client
regeneration, no migration, no mobile change.

## Deliberately unhandled

- **The misleading 502 copy.** "Could not analyze this photo" is right for users.
- **A contract test that calls OpenAI in CI.** It costs money per run and adds an
  outside dependency that can fail for unrelated reasons.
- **Isolating the lookahead from the union.** See the root cause note above.
- **Auditing other pydantic models for `Decimal`.** `ProviderFoodAnalysis` is the
  only model sent to a provider today.

## Open questions

None.
