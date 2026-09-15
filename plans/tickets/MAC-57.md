# MAC-57 implementation plan

## User outcome

A user can correct one food item, change its quantity, add a missed item, or remove an item. The
user can do this on the Review screen before saving a photo estimate, and on a saved entry
afterwards. Entry totals and day totals follow every change.

This is a vertical slice. It starts in the database totals math, crosses the API, and ends on two
screens a person can tap.

## Current behavior and sources

- `FoodItem` stores per-unit macros and a quantity. `FoodEntry` stores copied totals.
- `create_manual_entry` multiplies per-unit macros by quantity. `_store_photo_entry` writes each
  analysis item with quantity `1.00` and sums the item macros. The two paths compute totals with
  separate code, and no path recomputes totals after a write.
- `POST /api/entries/` accepts a Manual variant and a Photo variant. The Photo variant sends only
  `analysis_id`, so the server copies the model's numbers without any correction.
- The Review screen in `apps/mobile/app/(app)/photo.tsx` is read-only. MAC-54 deferred edits here.
- Today lists entries and items but no row opens anything.
- The canonical flow, section "Flow 3: review and correction", requires quantity change, name and
  portion change, macro edit, item removal, and item addition. Save recalculates entry and day
  totals.
- No visual export has Approved status for this screen. The implementation follows the canonical
  dark, number-first rules that MAC-54 and MAC-55 already use.

## Approach

### One totals rule, in one function

Add `entry_totals(items)` and `recalculate_entry_totals(entry)` to `entries/services.py`. The rule
is `sum(quantity * per_unit_macro)` for each of calories, protein, and fiber, quantized to two
places with `ROUND_HALF_UP`. `create_manual_entry`, the photo save, and every item write call it.

The photo path currently stores whole-item macros at quantity `1.00`, so the shared rule returns
the same numbers it returns today. Nothing about existing rows changes.

This exists because the entry totals are denormalized. The model docstring already says the
denormalization is only safe while one service owns both writes. Item editing adds three more
writers, so the shared function is what keeps that promise true.

### Correction after save: items are a sub-resource of an entry

Add three routes:

- `POST /api/entries/<int:entry_id>/items/` returns `201` and the created item.
- `PATCH /api/entries/<int:entry_id>/items/<int:pk>/` returns `200` and the updated item.
- `DELETE /api/entries/<int:entry_id>/items/<int:pk>/` returns `204`.

A URL names a resource, and an item only exists inside an entry, so the entry owns the collection.
The method supplies the verb. `PATCH` is right because the client sends the fields the user
changed. Each write runs in `transaction.atomic`, locks the parent entry with `select_for_update`,
applies the change, and then recalculates the entry totals. The lock serializes two concurrent
edits to the same entry, so the stored totals always match the stored items.

Ownership is a queryset filter, not a permission check: the view resolves the entry through
`daily_log__user=request.user` and returns `404` for anything else. A `404` does not tell a
stranger that the row exists.

Removing the last item returns `409` with a typed body,
`{"code": "entry_requires_one_item", "detail": ...}`. `409` is the status for a request that
conflicts with the current state of the resource. An entry with zero items has totals of zero and
no meaning, so the user deletes the entry instead. Entry deletion belongs to MAC-59, so this
ticket's copy points at that action without offering it yet.

### Correction before save: the save request carries the corrected items

Extend the Photo variant of `POST /api/entries/` with an optional `items` list. When it is absent
the server copies the analysis items, exactly as it does today. When it is present the server
validates the list with explicit serializers and stores those rows instead.

MAC-54 rejected this shape. The reason given was that client-supplied item values let a client
bypass the validated analysis. That reason does not hold once correction is the product: the same
user can already type any numbers through the Manual variant, and can edit the same rows one second
after saving through the routes above. The bypass is not new, and refusing it here would only
force the client to save wrong numbers and then immediately correct them.

The original estimate stays safe because `FoodAnalysisCall.response_payload` keeps the model's own
items. That row is what MAC-49 bills against and what explains a correction later. The entry rows
record what the user believes. The two are meant to differ.

The alternative, `PATCH /api/analyses/<id>/`, would edit the retained provider record. That record
is accounting data. A user edit must never touch it.

### Mobile

One editor component, `apps/mobile/components/item-editor.tsx`, renders the fields for one item:
name, portion, quantity, calories, protein, and fiber. It is a controlled component. It owns no
network calls and no persistence, so the two callers below decide what a change means.

Review, in `photo.tsx`, holds a corrected copy of the analysis items in React state. Edits, adds,
and removes change only that state. Totals recompute on the device with the same
`quantity * per-unit` rule. `SAVE TO TODAY` sends `analysis_id` plus the corrected items. Nothing
reaches the server until the user saves, so there is nothing to roll back.

A new route, `apps/mobile/app/(app)/entry/[id].tsx`, edits a saved entry. A Today row becomes a
link to it. The screen reads the entry from the cached day query, so this ticket adds no read
endpoint. Each change calls the API and updates the cached day optimistically: React Query's
`onMutate` writes the new item and the new entry and day totals into the cache, `onError` restores
the snapshot it took, and `onSettled` invalidates the day query so the server's numbers win. That
is the rollback the acceptance criteria ask for.

## Files touched

Backend:

- `apps/api/entries/services.py`: shared totals math, item add, item update, item remove, corrected
  photo save.
- `apps/api/entries/serializers.py`: `FoodItemWriteSerializer`, `FoodItemUpdateSerializer`, the
  optional `items` field on `PhotoEntryCreateSerializer`, and a shared "at least one positive macro"
  rule.
- `apps/api/entries/views.py`: `EntryItemListCreateView` and `EntryItemDetailView`, both with
  `@extend_schema` descriptions, parameters, examples, and the `409` response.
- `apps/api/entries/urls_entries.py`: the two nested routes.
- `apps/api/entries/tests/test_entry_items.py`: new test module.
- `apps/api/entries/tests/test_photo_entry.py`: corrected-items save cases.
- `packages/api-client/`: regenerated by `pnpm generate:api` and committed in the same PR.

Mobile:

- `apps/mobile/components/item-editor.tsx`: new shared editor.
- `apps/mobile/lib/entry-items.ts`: typed API helpers, the device-side totals rule, and the
  optimistic day-cache update and rollback.
- `apps/mobile/app/(app)/photo.tsx`: editable Review, add and remove, live totals, corrected save.
- `apps/mobile/app/(app)/entry/[id].tsx`: new saved-entry item editor.
- `apps/mobile/app/(app)/today.tsx`: entry rows open the editor.
- `apps/mobile/__tests__/`: new `entry-items.test.tsx` and `item-editor.test.tsx`, plus additions to
  `photo.test.tsx` and `today.test.tsx`.

No migration. `FoodItem` already has every field the editor writes.

## Django and React Native concepts in play

- **Denormalized totals and the single-writer rule.** Copied totals are fast to read and easy to
  break. One function owns the recalculation. This is the wrong choice as soon as anything writes
  `FoodItem` outside `entries.services`, for example the Django admin or a data migration.
- **`select_for_update` inside `transaction.atomic`.** The lock is on the parent entry, not the
  item, because the invariant being protected belongs to the parent. Locking the item would let two
  edits to different items of the same entry both recalculate from stale reads.
- **Queryset scoping as authorization.** Filtering by owner is stronger than a permission class
  because it cannot be forgotten on a second code path.
- **`PATCH` and partial serializers.** A partial update tells an omitted field from a cleared one.
  A `PUT` cannot, which is why the repo rules push back on it.
- **Optimistic updates in React Query.** `onMutate` returns a snapshot, `onError` restores it, and
  `onSettled` refetches. Optimism is wrong when a failed write is expensive to notice. Here the
  numbers reappear within one refetch, so it is safe.
- **Controlled components.** The editor takes a value and an `onChange`. It has no state of its own,
  so the same component works for unsaved analysis items and saved database rows.

## Tests

Backend:

- add an item, and confirm the entry totals and the day totals both move;
- change a quantity, and confirm per-unit macros multiply consistently;
- change a name, a portion, and each macro;
- reject a negative macro, a zero quantity, and an all-zero item;
- remove one item of several, and confirm the totals drop;
- remove the last item, and confirm `409`, the typed code, and no deletion;
- reject another user's entry and another user's item with `404`;
- confirm a failed write leaves the stored totals unchanged;
- save a photo entry with corrected items, and confirm the entry rows use the corrections while
  `FoodAnalysisCall.response_payload` keeps the model's original items;
- save a photo entry with no `items` field, and confirm current behavior is unchanged;
- reject corrected items that are empty or invalid;
- schema examples and generated-client drift.

Mobile:

- the editor renders and reports every field change;
- Review totals follow an edit, an add, and a remove;
- Review blocks removing the last item;
- save sends the corrected items;
- a Today row opens the saved-entry editor;
- an edit updates the cached totals before the response arrives;
- a failed edit restores the previous values and shows an error.

Then the full gate: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
`uv run pytest`, `pnpm generate:api`, `pnpm lint`, `pnpm format:check`, `pnpm check-types`,
`pnpm test`, and `git diff --check`.

## Alternatives rejected

- **A single `PUT /api/entries/<id>/items/` that replaces the whole list.** It cannot tell a cleared
  field from an omitted one, and it turns two users editing different items into a lost update.
- **`PATCH /api/analyses/<id>/` to correct before save.** It edits the retained provider record that
  MAC-49 bills against and that explains the correction.
- **Saving the estimate first and correcting afterwards.** It writes numbers the user already knows
  are wrong, and it leaves a wrong entry behind if the correction fails.
- **Returning the whole entry from every item write.** It reads well but breaks the `204` rule for
  a delete and makes the three responses inconsistent. The client invalidates the day query instead.
- **Computing entry totals on read.** Today renders these numbers on every frame. The denormalized
  totals exist for that reason, and MAC-55 already chose them.
- **A `corrected` flag on `FoodEntry`.** Comparing the entry items to the retained analysis payload
  answers the same question without a field that can drift.
- **Global macro steppers and an AI re-prompt.** Both are named out of scope in the ticket.

## Blast radius

The shared totals function touches both existing entry-creation paths, so a mistake there changes
every new entry. The tests pin the manual and photo numbers before and after the change.

Three new write endpoints can change any saved entry, so ownership scoping and the entry lock are
the controls that matter most in review.

The Photo save request gains an optional field. Old clients that omit it keep working.

Today rows become tappable. That is a navigation change on the app's main screen.

## Deliberately unhandled

Entry deletion, description editing, re-logging, past-day selection, and the full entry detail
screen belong to MAC-59. A second AI re-prompt, global macro steppers, recipes, meal grouping,
Recents, confidence display, and offline editing stay out. The saved-entry screen this ticket adds
is the minimum that makes correction after save real. MAC-59 grows it into entry detail rather than
replacing it.

## Open questions

1. The saved-entry editor lands as a small screen now, because the acceptance criteria need
   correction after save to work end to end. Confirm that MAC-59 extends this screen instead of
   building a new one.
2. Correcting before save now sends item values in the save request. MAC-54 rejected that shape.
   Confirm the reversal, and the reasoning above.

## Approval gate

Implementation starts after Alex approves this plan.
