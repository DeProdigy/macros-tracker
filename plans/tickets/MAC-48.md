# MAC-48 implementation plan

## User outcome

A user can log against the same calendar day that the phone displays.

## Current behavior

The user model and current-user endpoint already store a timezone string. The API accepts any string. The mobile app never reads or synchronizes the device timezone. Target saving has a private local-date formatter, but future entry requests have no shared timezone readiness contract.

## Files and layers

- Update the account settings serializer and its tests to validate IANA timezone names.
- Add `apps/mobile/lib/local-day.ts` for device timezone detection, local date formatting, and the day-request readiness check.
- Update `apps/mobile/lib/target-save.ts` to reuse the shared local-date formatter.
- Update `apps/mobile/lib/session.tsx` to synchronize timezone after restore, after sign-in, and when the app returns to the foreground.
- Extend session and local-day tests.
- Regenerate the API client only if schema generation changes the contract.

## Approach

The server validates timezone names with Python's standard `zoneinfo` database. It rejects numeric offsets and unknown names before saving.

The mobile helper reads `Intl.DateTimeFormat().resolvedOptions().timeZone`. It formats dates from the phone's local calendar fields instead of converting through UTC. A day-request helper requires a synchronized timezone state and throws a named recoverable error when that state is unavailable.

The session provider starts a best-effort synchronization after authentication succeeds. It updates the cached user after a successful PATCH. A failed timezone read or PATCH leaves authentication intact and marks day-based work unavailable. An AppState active event repeats the comparison so travel or a system timezone change can update the server.

## Alternatives rejected

- Do not store a numeric UTC offset. Offsets change during daylight-saving transitions and do not identify a timezone.
- Do not let the server infer the user's calendar day. The phone owns the local date contract.
- Do not block sign-in on the PATCH. Timezone synchronization is required for day-based logging, not authentication.
- Do not silently use UTC after a failure. That can put food on the wrong day.
- Do not add background monitoring. Foreground synchronization covers the supported app lifecycle.

## Concepts

The Django work uses serializer validation and the standard IANA timezone database. The React Native work uses AppState lifecycle events, a best-effort post-auth synchronization effect, and explicit readiness state for a later vertical slice.

This horizontal ticket uses the safety-control exception. Timezone readiness must exist before the food-entry slice that it guards, so that slice cannot silently assign food to the wrong day.

## Tests

- Accept valid IANA names such as `America/New_York` and `Pacific/Auckland`.
- Reject unknown names and numeric offsets.
- Format local dates without UTC rollover.
- Preserve daylight-saving timezone identity.
- Synchronize after restore and sign-in.
- Avoid a PATCH when the stored timezone already matches.
- Synchronize a changed timezone when the app returns to the foreground.
- Keep the user signed in and mark day requests unavailable when synchronization fails.
- Run backend tests, mobile Jest, type checks, lint, formatting checks, API-client drift, and `git diff --check`.

## Blast radius and exclusions

The change affects account settings validation, session state, and shared date helpers. It does not add entry models, food screens, offline replay, multi-device resolution, or background timezone monitoring.

## UI evidence

This issue adds no user-visible screen. Pull request screenshots are not applicable.

## Open questions

None. The canonical architecture and MAC-48 define the ownership and failure behavior.
