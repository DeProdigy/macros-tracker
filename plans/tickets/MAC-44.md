# MAC-44 implementation plan

## User outcome

An onboarded user can see current targets, set a new target version, and review earlier versions from Settings.

## Current behavior

Settings has a plain link to the existing target editor. The editor loads the current target and creates an append-only version. The API already exposes the current target singleton and the complete version collection in newest-first order. No target history screen exists.

## Files and layers

- Update `apps/mobile/app/(app)/settings.tsx` to load and display current targets. Add Adjust and History actions.
- Add `apps/mobile/app/(app)/target-history.tsx` for the target version list and its loading, empty, and failure states.
- Reuse `apps/mobile/app/targets.tsx` for edits. Keep its current save and return behavior.
- Extend mobile tests for Settings, target editing, and target history.
- Do not change Django or the generated API client. The required endpoints and types already exist.

## Approach

Settings reads the current-target singleton when it gains focus. This makes a newly saved version visible when the editor returns to Settings. The history screen reads the append-only target collection.

The history screen shows each stored effective date with its year. It does not infer an end date. Creation order and effective dates can differ, and two versions can start on the same day. Cards show the stored source and all three target values. An onboarding rationale appears when one exists. A manual version does not receive invented explanatory copy.

The screens use the canonical dark visual system. The Candidate Settings and target-history images provide composition context only. They are not implementation authority because Alex has not approved them.

## Alternatives rejected

- Do not add `/api/targets/history/`. The existing target collection is the history resource.
- Do not combine the singleton and history reads. The ticket explicitly requires the singleton for current targets, and Settings does not need the full collection.
- Do not infer or store an end date. The API does not promise that creation order and effective dates stay aligned. An inferred range can run backwards when two versions share a date.
- Do not refresh Settings only after a local save callback. A focus refresh also covers deep links and changes from another route.

## Concepts

The React Native work uses Expo Router navigation and focus-based refresh. The history list uses derived presentation data rather than duplicating domain state. The Django model remains a slowly changing dimension: a change appends a row instead of editing one.

## Tests

- Settings shows current targets and both actions.
- Settings shows loading, empty, and retryable failure states.
- Settings refreshes after it regains focus.
- History renders newest first with effective dates, years, and sources.
- History renders two versions on the same effective date without a false range.
- History renders its loading, empty, and retryable failure states.
- The existing editor still saves a new version and returns to Settings.
- Run mobile Jest, type checks, lint, formatting checks, and `git diff --check`.

## Blast radius and exclusions

The change affects Settings, navigation to the existing editor, the new history route, and mobile tests. It does not change migrations, API schemas, generated code, old target rows, prior days, target advice, coaching, weight history, or the wider Settings design.

## UI evidence

Capture live Settings, populated history, empty history, and failure states. Upload them to the pull request only. Do not commit review screenshots.

## Open questions

None. The canonical documents and MAC-44 settle the required behavior.
