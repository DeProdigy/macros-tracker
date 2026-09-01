# MAC-55 implementation plan

## User outcome

A user can enter one food item manually, save it to the phone's selected local day, and immediately see that item and its macro totals on Today.

## Vertical slice

This ticket is one complete vertical slice. It starts at the Manual action, crosses the generated client and authenticated API, stores the entry transactionally, and ends with refreshed Today totals and an entry row.

A user can now log a meal manually and see it counted on Today.

## Canonical sources

- `plans/start-here-product-scope-and-sources-of-truth.md` defines the MVP boundary.
- `plans/canonical-mvp-experience-and-screen-flows.md` defines Manual logging and Today behavior.
- `plans/canonical-engineering-baseline-and-mvp-architecture.md` defines DailyLog, FoodEntry, FoodItem, local-date ownership, and generated-client use.
- `plans/canonical-mvp-visual-design-and-approved-screens.md` defines the visual system.
- Source images `10-log-capture-manual.png`, `16-today-first-run.png`, `17-today-empty-day.png`, and `19-today-normal.png` are Candidate artifacts only. They can help identify the existing direction, but they do not override the canonical documents. No approved export exists for this slice.

## Backend

Create an `entries` Django app with these resources:

- `DailyLog`: unique by user and `local_date`; captures the target version that applies when the day is first created.
- `FoodEntry`: belongs to one DailyLog; stores source, description, eaten time, aggregate calories, protein, and fiber.
- `FoodItem`: belongs to one FoodEntry; stores name, optional portion label, quantity, and per-unit calories, protein, and fiber.

The save service will use one database transaction. It will get or create the user's DailyLog, create one Manual FoodEntry and one FoodItem, calculate entry totals from quantity times the per-unit values, and store the aggregate once. The API will not accept aggregate totals from the client.

Add two authenticated resource routes:

- `POST /api/entries/` creates a Manual entry. The request contains `local_date`, `timezone`, `eaten_at`, and one item.
- `GET /api/days/<date>/` returns the selected day, captured targets, totals, and entries in reverse chronological order.

The create endpoint will reject a timezone that does not match the synchronized user timezone. It will validate the local date without deriving it from the server clock. It will reject blank names, nonpositive quantity, negative macro values, values outside database precision, and access outside the authenticated user's rows.

The day endpoint is scoped through the authenticated user. A date with no DailyLog returns an empty day response instead of creating a row during a read.

## Mobile

Add a signed-in logging route with a Manual form for name, calories, protein, fiber, and quantity. Photo and Recents remain visible as equal choices but disabled with honest follow-up copy because they are outside MAC-55.

The first-food prompt and Today Log food action open the same logging route. Saving uses `localDayContext`, the synchronized user timezone, and the current local time. A timezone-sync failure keeps the entered values and shows a recoverable retry state.

Replace the Today placeholder with:

- the selected local date;
- calorie, protein, and fiber totals for the day;
- a flat reverse-chronological entry list;
- a clear empty state;
- a persistent Log food action.

Finished rings, target progress tiles, past-date selection, entry detail, editing, deletion, photos, Recents, and animation remain follow-ups. After save, invalidate the selected-day query and return to Today so the new entry appears from server state.

## Validation and numeric decisions

Use decimal quantity with two fractional places and a positive lower bound. Store per-unit macro values with two fractional places so quantity scaling does not lose information. Return displayed totals as rounded decimal values from the API contract. Calories, protein, and fiber accept zero but not negative values. At least one macro must be greater than zero.

Use the item name as the entry description for this one-item Manual slice. Keep `portion_label` empty until a later correction or Recents slice supplies it.

## Tests

Backend tests will cover model ownership and uniqueness, captured targets, transactional save, derived totals, empty and populated day reads, reverse chronology, authentication, cross-user isolation, date and timezone validation, and numeric bounds.

Schema and generated-client checks will prove the request and response types. Mobile tests will cover first-food navigation, Manual validation, successful save, retained input on failure, timezone-unavailable behavior, Today empty and populated states, totals, list ordering, and query refresh after save.

Run migrations, the complete backend suite, Ruff, mypy, OpenAPI generation and drift checks, TypeScript, ESLint, Prettier, the complete mobile Jest suite, and `git diff --check`.

## UI evidence

This ticket changes UI. The PR will include screenshots of the Manual form, validation state, empty Today state, and populated Today state. Screenshots are review artifacts and will not be committed to the repository.

## Blast radius and exclusions

The change adds persistent food-domain tables and two public API resources. It changes the first-food handoff and Today screen. It does not call AI, upload to R2, create Recents search, support offline writes, or add entry correction and deletion.

## Approval gate

Implementation starts only after Alex approves this plan. The main assumptions to approve are the two resource routes, per-unit macro storage with decimal quantity, empty reads that do not create DailyLog rows, and the reduced Today presentation for this slice.
