# MAC-56 implementation plan

## User outcome

A user can find a food they logged before, choose a new quantity, preview the resulting macros,
and save it as a new entry without taking a photo or invoking AI.

## Files touched

- `apps/api/config/urls.py`: expose the food-history collection at `/api/foods/`.
- `apps/api/entries/urls_foods.py`: route the food-history list endpoint.
- `apps/api/entries/services.py`: query distinct recent foods and create copied Recent entries.
- `apps/api/entries/serializers.py`: define recent-food responses and Recent entry requests.
- `apps/api/entries/views.py`: serve searchable Recents and dispatch the third entry-create shape.
- `apps/api/entries/tests/`: cover distinct history, search, ownership, copying, and side effects.
- `apps/mobile/app/(app)/log-food.tsx`: enable the Recents search, preview, and save flow.
- `apps/mobile/__tests__/log-food.test.tsx`: cover Recents states and entry creation.
- `apps/mobile/__tests__/today.test.tsx`: verify no-photo Recent entries on Today.
- `apps/mobile/__tests__/entry-editor.test.tsx`: verify no-photo Recent entries in Entry Detail.
- `packages/api-client/openapi.json`: record the new endpoint and entry request variant.
- `packages/api-client/src/`: regenerate typed models, endpoints, and React Query hooks.

## Approach

Add an authenticated `GET /api/foods/?search=` collection endpoint. It reads the current user's
historical `FoodItem` rows newest-first by entry eaten time, then entry and item identifiers for
stable ties. It normalizes trimmed, case-folded name and portion-label values to collapse matching
items, retaining the newest row's macro snapshot. The optional query searches names and portion
labels case-insensitively. Different portions of the same food remain separate choices.

Extend `POST /api/entries/` with a Recent request variant containing `recent_item_id`, quantity,
local date, timezone, and eaten time. The service loads that item through the authenticated user's
history, creates a new `FoodEntry` with source `Recent`, copies the item's descriptive and per-unit
macro fields, applies the chosen quantity, and recalculates totals in one transaction. The original
entry and item remain unchanged, and invalid or cross-user identifiers receive a field validation
error without exposing another user's data.

Enable the existing Recents choice on the Log Food screen rather than adding a new route. The view
will show loading, error, empty, search-result, selected-item, and save-error states. Selecting an
item starts at quantity one; quantity edits use the existing exact decimal helpers so the displayed
preview matches the server's saved totals. A successful save invalidates both the day and recent-food
queries and returns to Today. A failed save preserves the search, selection, and quantity.

Debounce the trimmed search term for 300 milliseconds before changing the generated query key. This
keeps search server-owned and case-insensitive without issuing one request for every keystroke.

Keep Today and Entry Detail source-agnostic. Their existing nullable-photo behavior should already
support Recent and Manual entries, so add explicit regression tests and only change production UI if
those tests reveal a no-photo rendering defect.

Document both endpoint shapes with explicit OpenAPI descriptions, parameters, responses, and
examples, regenerate the client, and consume only generated request types and hooks in the app.

## Alternatives rejected

- A saved-food or favorites model would turn event history into a separate library outside this slice.
- `/api/foods/recent/` would encode a UI concept in the route instead of using a resource collection.
- Sending macro values back from the client would trust stale or manipulated data rather than the
  authenticated source snapshot.
- Updating the historical item would violate the requirement that re-logging creates a new event.
- A dedicated Recents screen would split the approved equal-choice Log Food surface without an
  approved design artifact requiring that navigation.
- Database-specific `DISTINCT ON` or window expressions would make normalization and ordering harder
  to express consistently; ordered application-level deduplication is sufficient for personal MVP
  history and keeps Unicode case folding explicit.

## Concepts in play

- Django ownership filtering prevents recent-item identifiers from crossing user boundaries.
- Transactional snapshot copying preserves history while allowing later entries to diverge.
- Ordered projection and normalized composite keys implement newest-wins distinct Recents.
- Serializer request variants keep Manual, Photo, and Recent creation explicit under one resource.
- React Query keys and invalidation keep the day and Recents list synchronized after creation.
- A short client debounce reduces superseded search requests while preserving server-side filtering.
- Integer-backed decimal helpers keep quantity previews aligned with persisted macro totals.

## Blast radius

The change adds one authenticated read endpoint, a third request shape to the existing entry-create
endpoint, generated-client updates, and Recents UI behavior on the current Log Food screen. It does
not require a database migration or change Photo and Manual entry persistence. Today and Entry Detail
receive regression coverage for nullable photos but should not need behavioral changes.

## Deliberately unhandled

This slice does not add favorites, a permanent food library, recipes, barcode scanning, offline
storage, editing historical entries, whole-entry re-logging, past-day logging, pagination, or new
database indexes. Those remain separate product or scaling decisions.

## Open questions

None. The ticket and canonical product, visual, and architecture documents define the resource,
distinctness rule, current-time semantics, source value, and no-AI boundary.
