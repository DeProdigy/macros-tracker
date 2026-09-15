# MAC-59 implementation plan

## User outcome

A user can select Today or a past day, open one entry, see its retained details, edit its items,
log the whole entry again, or delete it without developer help.

## Files touched

- `apps/api/entries/services.py`: read, copy, and delete owned entries with photo reference safety.
- `apps/api/entries/serializers.py`: define entry-copy requests and logged-day summaries.
- `apps/api/entries/views.py`: add entry detail and day collection behavior.
- `apps/api/entries/urls_entries.py`: route one entry resource by identifier.
- `apps/api/entries/urls_days.py`: route the filtered day collection.
- `apps/api/entries/tests/`: cover ownership, copy, delete, photo cleanup, and day summaries.
- `apps/mobile/app/(app)/today.tsx`: select and render Today or a past day.
- `apps/mobile/app/(app)/entry/[id].tsx`: show full detail, edits, re-log, and delete behavior.
- `apps/mobile/app/(app)/log-food.tsx`: create Manual and Recent entries on the selected day.
- `apps/mobile/app/(app)/photo.tsx`: save a Photo entry on the selected day.
- `apps/mobile/components/`: add a reusable calendar sheet if the screen remains readable with one.
- `apps/mobile/lib/local-day.ts`: build valid timestamps for an explicit local date.
- `apps/mobile/lib/entry-items.ts`: keep day and entry-detail caches synchronized after item edits.
- `apps/mobile/__tests__/`: cover selected-day navigation and entry-detail states and actions.
- `packages/api-client/openapi.json`: record the new endpoint and request contracts.
- `packages/api-client/src/`: regenerate models, endpoints, and React Query hooks.

## Approach

Add `GET /api/entries/{id}/` and `DELETE /api/entries/{id}/`. Both operations filter by the
authenticated user. The detail response reuses the complete `FoodEntry` representation. Deletion
removes the database row in one transaction. An `on_commit` callback deletes the R2 object only when
the deleted entry had a photo key and no remaining entry references that key. An object-storage
failure is logged after the committed deletion and does not change a successful API result.

Extend `POST /api/entries/` with a whole-entry re-log request that contains `source_entry_id`, local
date, timezone, and eaten time. The service reads the owned source entry with its items, creates a new
`Recent` entry, and copies every item snapshot. It does not copy the photo or call AI. The mobile
detail action targets Today and uses the current time, as the approved artifact specifies.

Add `GET /api/days/?month=YYYY-MM`. It returns the owned local dates that contain entries in the
requested month. The calendar uses these dates as markers and continues to read the selected day
through `GET /api/days/{local_date}/`. The collection route stays before the detail route so the
empty path cannot collide with a date.

Keep the selected date in the Today route parameters. Today defaults to the device local date and
opens a custom calendar sheet from its date title. The calendar does not add a native-only package.
It supports month movement, marked logged days, one selected day, past dates, and Today. Future dates
remain unavailable because the ticket covers Today and past days.

Pass the selected date through Today, Entry Detail, Log Food, and Photo routes. Manual, Recent, and
Photo saves use the explicit selected date. A shared helper combines that date with the current local
clock time and synchronized timezone so the API receives matching `local_date` and `eaten_at` values.
Successful saves return to the selected day rather than silently returning to Today.

Change Entry Detail to use the new entry resource instead of scanning one day response. It shows the
retained photo when present, source, time, description, totals, and editable items. It keeps the
existing item correction controls. Item mutations update or invalidate both the entry detail and its
source-day query.

Add a whole-entry Log Again action and a destructive delete confirmation. The confirmation names the
entry and the totals that leave the day. It does not mention streaks. A successful re-log invalidates
Today and Recents and opens Today. A successful delete removes the detail cache, invalidates the
source day and Recents, and returns to the preserved source day.

## Alternatives rejected

- A separate history screen duplicates the selected-day view and is outside the canonical navigation.
- A verb route such as `/api/entries/{id}/re-log/` violates the resource route rules. Entry creation
  remains `POST /api/entries/` with a distinct request shape.
- Copying the photo during re-log conflicts with the approved no-photo and no-AI behavior.
- Reusing `GET /api/days/{date}/` for entry detail forces the client to fetch and scan an unrelated
  collection. The ticket explicitly adds entry-detail read behavior.
- A native date-picker dependency gives iOS, Android, and web different behavior. A small shared
  calendar keeps the approved states testable across current targets.
- A free-form date field does not match the approved date-picker interaction and permits invalid input.
- Deleting the R2 object inside the database transaction cannot roll back the object deletion if the
  database later fails. The post-commit cleanup makes database state authoritative.

## Concepts in play

- Ownership-filtered detail queries prevent cross-user reads and mutations.
- Snapshot copying creates a new food event without rewriting history.
- Database commit hooks separate transactional rows from non-transactional object storage.
- Reference checks prevent one deletion from removing a photo that another entry still uses.
- Route parameters preserve navigation context without adding global selected-day state.
- Local wall-clock composition keeps explicit past dates consistent with the stored timezone.
- React Query cache keys keep entry detail, day totals, and Recents synchronized.
- A month-filtered resource collection supplies bounded calendar markers.

## Blast radius

The change adds one entry detail route, one filtered day collection route, and one entry-create request
shape. It changes Today from a fixed current-day view to a selected-day view. It passes date context
through all three logging modes and expands Entry Detail from item correction to full entry management.
It regenerates the API client. It does not require a database migration.

## Deliberately unhandled

This ticket does not add analytics history, weekly reports, streak consequences, multi-device conflict
resolution, offline sync, future-date logging, entry description editing, photo replacement, photo
re-analysis, or photo copying during re-log. The active issue does not include these behaviors.

## Open questions

None. The ticket and canonical documents define the selected-day behavior. The approved artifacts
define the no-photo re-log and no-streak delete presentation.
