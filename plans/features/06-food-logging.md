# 06 — Feature: Food Logging

## The core loop

Snap or pick a photo → add a short description → AI estimates macros → review and correct → save.

This is the feature the app lives or dies on. Every second of friction here costs a logged meal.

## Capture

Two entry points, equal weight:

* **Camera** — `expo-camera` or `expo-image-picker` in camera mode
* **Library** — `expo-image-picker`, for food photographed earlier

Permissions must be requested with context, at the moment of use, not on app launch. iOS users deny blanket permission requests. Handle denial gracefully with a path to settings.

## Compression — do this before upload

A modern iPhone photo is 3–5 MB. The vision API does not need that, the user's cellular data does not deserve it, and R2 storage is not free.

Resize to roughly 1024px on the long edge, JPEG quality ~0.7, via `expo-image-manipulator`. Typical result is 150–300 KB — an order of magnitude smaller with no meaningful loss in estimation accuracy.

Skipping this step is the single most common performance mistake in photo-based mobile apps.

## Upload path

**Presigned direct-to-R2 upload**, not proxying bytes through Django:

1. Client requests a presigned PUT URL from the API
2. Client uploads the image directly to R2
3. Client sends the object key to the API with the entry payload

Why: image bytes never touch the application server, so it doesn't tie up a worker for the duration of a slow mobile upload. This is a standard pattern worth knowing cold — it comes up in system design interviews constantly.

## Analysis

```
POST /api/entries/analyze/    photo_key, description → estimate (not persisted)
```

Returns proposed calories, protein, fiber, plus a brief note on what the model saw. **Nothing is saved yet.**

Prompt design lives in the `ai` app. Requirements:

* Demand strict JSON output; parse it, reject malformed responses
* Instruct the model to reason about portion size explicitly — that's the dominant error source, not food identification
* The user's description is a strong signal. "Grilled chicken, about 8oz, and a cup of rice" should override what the photo suggests
* Return a confidence signal if practical, so the UI can nudge harder toward review on low confidence

## Correction — both paths, per the product decision

**Path 1: inline edit.** Numbers are editable fields on the review screen. Change 620 to 480, save. Sets `was_edited = true`.

**Path 2: re-prompt.** Amend the description ("that's egg whites, not whole eggs") and re-analyze. New estimate, replaces the old one.

Keep the original AI response in `ai_raw_response` regardless. It costs nothing and it's the only way to ever evaluate how good the estimates actually are.

## Save

```
POST /api/entries/    photo_key, description, macros, local_date → FoodEntry
```

Server resolves `get_or_create(DailyLog, user, local_date)`, attaches the current `TargetVersion` if the day is new, creates the entry.

The client sends `local_date` — its own calendar date. See the data model doc for why.

**Log to a previous day:** the same endpoint with a different `local_date`. No special handling needed; this is the payoff of the DailyLog design.

## Latency

The analyze call takes several seconds. Synchronous in v1 — no Celery, per the architecture doc.

The mobile app absorbs this with a real loading state: show the compressed photo immediately, indicate analysis in progress, keep the UI responsive. Perceived performance is mostly about not looking frozen.

If p95 becomes genuinely painful, that's the evidence needed to justify a queue. A spike ticket tracks it.

## Editing and deleting

* Edit an existing entry's macros or description
* Delete an entry; if it was the day's last, the `DailyLog` stays (an empty day is not the same as a day that never existed — though note this does affect the streak query, so decide deliberately)
* Deleting an entry should also clean up its R2 object

## What you're learning here

* Camera and media library APIs, and permission UX on iOS
* Client-side image manipulation and why it matters
* Presigned upload patterns and offloading work from the app server
* Vision-model prompting and structured output extraction
* Optimistic vs. pessimistic UI updates with React Query
* Designing for AI fallibility — the correction flow is the real product insight here
