# MAC-76: Return photo-analysis counts as item quantity

Status: approved by Alex on 18 Sep 2026.

Linear: https://linear.app/hintology/issue/MAC-76/return-photo-analysis-counts-as-item-quantity

## The bug

`ProviderFoodItem` has a name, a portion, and three macros. It has no
quantity. So the model has nowhere to put a count and puts it in prose.

A photo of four boiled eggs comes back as one item named "4 boiled eggs" with
the macros for all four. `analysisItemToEditable` in
`apps/mobile/lib/entry-items.ts:35` then hardcodes `quantity: "1.00"`.

The screen looks right. The stored row is a lie. It claims one unit of a thing
called "4 boiled eggs", so the quantity is 1 and the per-unit macros are
really four units of macros.

Three features read that row and start from the wrong number.

1. **Quantity editing.** Stepping that item to 2 asks for eight eggs and gets
   four eggs' macros doubled, which is right by accident. Stepping it to 1
   leaves four eggs. There is no way to say "actually three eggs".
2. **Per-unit macro maths.** `itemTotals` multiplies quantity by each macro.
   With quantity pinned at 1 that multiplication never does anything.
3. **Recents.** Re-logging "4 boiled eggs" at quantity 2 silently means eight.

## The shape it has to produce

| Field | Now | After |
| -- | -- | -- |
| `name` | `4 boiled eggs` | `boiled egg` |
| `portion` | `4 eggs` | `1 egg` |
| `quantity` | absent, forced to `1.00` | `4.00` |
| `calories`, `protein_g`, `fiber_g` | all four eggs | one egg |
| analysis totals | all four eggs | all four eggs, unchanged |

The totals stay the same number. They are computed differently.

## The constraint that shapes the whole ticket

`quantity` must be a `float` on `ProviderFoodItem`, not a `Decimal`.

MAC-72 already paid for this. The comment above that class says it: pydantic
renders a `Decimal` field as `anyOf: [number, string-with-pattern]`, the
pattern holds a negative lookahead, and OpenAI cannot compile that into a
decoder grammar. The call then returns `status=incomplete` with
`reason=max_output_tokens` and zero tokens used, which is a budget error that
has nothing to do with budget. The three macro fields already made this
compromise.

`Decimal` comes back at the Django boundary, where this app owns its own
types and nobody has to negotiate with a third party's grammar compiler.

### The bound on the provider field, and why it is `ge=0`

The obvious choice is `Field(gt=0)`, because a quantity of zero is nonsense.
That renders `exclusiveMinimum`. The three macro fields use `Field(ge=0)`,
which renders `minimum`, and that shape is proven in production.

The risks are not symmetric. If `exclusiveMinimum` does not compile, **every**
analysis call fails, and it fails with the same misleading budget error MAC-72
spent a ticket chasing. If `ge=0` lets a zero through, one call fails at the
Django boundary and the user retries.

So the provider schema uses `ge=0`, matching the fields that already work, and
Django rejects zero. The prompt also tells the model the count is at least 1.
This is the same trade the macros made, for the same reason.

## Files

### API

| File | Change |
| -- | -- |
| `ai/provider.py` | Add `quantity: float = Field(ge=0)` to `ProviderFoodItem`. Rewrite `FOOD_ANALYSIS_INSTRUCTIONS` to ask for a singular name, a one-unit portion, a count, and per-unit macros |
| `ai/serializers.py` | Add `quantity` to `FoodAnalysisItemSerializer`, matching the bounds `entries/serializers.py` already uses |
| `ai/services.py` | Round and carry `quantity`. Compute totals as quantity times per-unit |
| `ai/tests/test_analysis_service.py` | Repeated item, single item, invalid quantity, totals maths |
| `ai/tests/test_serializers.py` | Boundary validation on the new field |
| `entries/tests/test_photo_entry.py` | A returned quantity survives the save |

### Mobile

| File | Change |
| -- | -- |
| `lib/entry-items.ts` | `analysisItemToEditable` reads `item.quantity` instead of hardcoding `"1.00"` |
| `__tests__/entry-items.test.tsx` | The mapper carries quantity, and totals agree with the server |
| `__tests__/photo.test.tsx` | Review starts from the returned quantity and stays editable |

### Generated

`packages/api-client` and `apps/api/openapi.json`, both from
`pnpm generate:api`, committed in the same PR. CI fails on drift.

## The totals calculation, which is the subtle part

Today `ai/services.py:327` sums the per-item macros and nothing multiplies:

```python
calories=_rounded_macro(sum(Decimal(item["calories"]) for item in items)),
```

Mobile already multiplies. `itemTotals` in `lib/entry-items.ts:154` sums
`quantity × macro` in integer hundredths and rounds once at the end.

The two agree today only because quantity is always 1. The moment quantity can
be 4, they disagree unless the server changes too.

They also have to agree on **when** they round. Mobile sums the exact products
and rounds the sum once. Rounding each product first and then summing gives a
different answer on values ending in half a cent, which is exactly the case a
reviewer would never think to check and a user would hit within a week.

So the server sums exact `Decimal` products and quantizes once, matching
mobile. A test asserts a case built to round differently under the two orders,
so the next person to touch either side finds out immediately.

## Alternatives rejected

**Parse the count out of the name in Django or React Native.** This is the
obvious cheap fix and the ticket rules it out. It means owning English
pluralisation forever: "4 boiled eggs", "a couple of eggs", "half an avocado",
"2x toast". Every one of those is a bug report. The model already knows the
count; the schema just never gave it a place to put it.

**Ask the model for the count in the portion string and parse that.** Same
problem, smaller words.

**Make the model return one row per egg.** Four rows named "boiled egg" with
quantity 1. Technically correct and horrible to review. The ticket rules it
out under "splitting visibly different foods into one row", and the inverse is
just as wrong.

**`Decimal` on the provider schema.** See the constraint section. This is the
one that looks right and breaks every call.

**Backfill existing `FoodItem` rows.** Out of scope, and I agree. The old rows
say "4 boiled eggs, quantity 1" and the totals on those days are correct. A
backfill would have to guess the count from text, which is the parser this
ticket exists to avoid.

## Django and React Native concepts in play

- **A provider schema is a wire format, not a domain model.** It is bound by
  what a third party's grammar compiler accepts. The existing comment on
  `ProviderFoodItem` makes this point and this ticket is the second time it
  has mattered.
- **Validate at the boundary.** The model is an untrusted input. DRF
  serializers are where the app decides what it will accept, and the bounds
  should match the ones the save path already enforces, or the two disagree.
- **Decimal against float.** Money-shaped and count-shaped values want exact
  decimal arithmetic. `_rounded_macro` already converts with
  `Decimal(str(value))` because `str()` on a float gives the shortest string
  that round-trips.
- **Rounding order changes the answer.** Sum-then-round and round-then-sum are
  different functions. Two codebases computing the same total must pick the
  same one.

## Blast radius

The photo analysis path only. Manual logging, Recents, the day resource, and
every screen outside photo review are untouched.

The generated client changes, so `pnpm generate:api` runs and the result is
committed. That is a real diff a reviewer sees.

Nothing changes in the database. `FoodItem.quantity` already exists as
`DecimalField(max_digits=8, decimal_places=2)`, so there is no migration.

## Deliberately unhandled

- **Old rows.** No backfill. Their totals are already right.
- **Singularisation.** The model returns the singular name. Nothing in this
  repo learns English.
- **Splitting mixed items.** Two different foods stay two rows. Four identical
  ones become one row with a count.
- **The `FoodEntry` description.** Out of scope, and separate from the item
  `name` this ticket changes.

## Open questions

1. **The upper bound on quantity.** `FoodItem.quantity` is
   `max_digits=8, decimal_places=2` and mobile caps at `999999.99`. I plan to
   use the same bound on the analysis serializer so the two boundaries cannot
   disagree. It is a strange number for food, but a second, tighter limit that
   only the analysis path enforces is worse: a value the model returns would
   pass review and fail on save.
2. **What a zero should do.** I plan to fail the whole analysis as invalid
   model output, which is what the acceptance criteria say. The alternative is
   clamping to 1, which hides a model that is not following instructions.
   Failing costs the user one retry and tells us the prompt needs work.
