# MAC-54 implementation plan

## User outcome

A user can take or choose one meal photo, add an optional description, receive itemized calorie,
protein, and fiber estimates, review them, and save one Photo entry to Today.

This is a vertical slice. It starts with native photo input, crosses R2 and the paid model boundary,
and ends with durable entry and item rows that the existing Today query returns.

## Current behavior and sources

- The logging screen supports Manual only. Photo and Recents are inactive labels.
- `POST /api/uploads/` returns a presigned pending R2 upload. The mobile app does not call it yet.
- `uploads.services` can promote a pending key to `entries/`, but no entry stores a photo key.
- MAC-49 records model attempts and enforces the rolling quota before provider dispatch.
- MAC-55 stores Manual entries and returns itemized entries on the day resource.
- The canonical experience defines capture, description, compression, upload, analysis, review,
  save, and return to the selected day. It requires retained input after a retryable failure.
- No visual export has Approved status. The implementation uses the canonical dark, number-first
  visual rules. Candidate files do not define presentation.

## Mobile flow

Turn `log-food` into the shared entry-choice screen with working Photo and Manual choices. Recents
stays visible and unavailable. Keep the Manual form behavior from MAC-55.

Add a Photo route with these states:

1. The capture state offers Camera and Library as equal inputs.
2. The camera path requests camera permission. A denial keeps Library available and offers a link
   to iOS Settings.
3. Both inputs produce the same selected-photo state and optional description field.
4. The client uses Expo Image Manipulator to correct orientation, resize the long edge to a fixed
   ceiling, and encode JPEG at a fixed quality. It then requests a presigned upload and sends the
   exact content type and byte length that the signature covers.
5. The client uploads directly to R2 and creates an analysis with the returned object key and
   description.
6. The Review route leads with aggregate calories, protein, and fiber. It lists each returned name,
   portion, and macro estimate. MAC-57 owns edits, additions, removals, and quantity correction, so
   this screen is read-only in this ticket.
7. Save sends the analysis identifier plus the local date, timezone, and eaten time. It invalidates
   the existing day query and returns to Today.

Keep the selected local URI and description in route-scoped React state while the Photo screen is
mounted. Upload and analysis errors do not clear them. Retry repeats compression, upload, and
analysis with a fresh pending key. Manual opens the existing Manual form. The quota state uses its
typed error details and does not show an invented calendar reset date.

Use `expo-image-picker` for camera and library permissions and `expo-image-manipulator` for local
compression. These Expo modules keep native permission declarations and image transforms inside
the managed app configuration. Jest mocks the native boundary. A physical iPhone proves the real
camera, permission prompt, image orientation, upload, and R2 behavior.

## Analysis API and provider boundary

Add `POST /api/analyses/`. The request contains a pending R2 key and an optional description. The
response contains an analysis identifier, aggregate totals, and validated items. The route creates
a computed analysis resource and returns `201` because the retained `FoodAnalysisCall` gives the
result a durable server identity.

The analysis service performs this sequence:

1. Validate that the pending key belongs to the authenticated user.
2. Reserve a call through MAC-49. A quota rejection creates no call and maps to the existing typed
   `food_analysis_quota_exceeded` response.
3. Move the image from `pending/` to an `analyses/{user_id}/...` key before provider dispatch. This
   preserves the image that the retained request and response snapshots describe, even if the user
   never saves the estimate.
4. Create a short R2 download URL only for provider input. Do not store that URL in Postgres.
5. Mark the reservation dispatched and call the OpenAI Responses API with the image, a prompt that
   treats the user's description as strong evidence, and a strict JSON schema.
6. Validate the decoded result again with explicit DRF serializers. Require at least one item.
   Require nonblank names and portions, quantity `1.00`, nonnegative macros, database-safe decimal
   precision, and at least one positive macro across the result. Calculate aggregate totals on the
   server from the item values.
7. Finalize the MAC-49 row with provider metadata, usage, estimated cost, and the raw structured
   result. Return only the validated representation.

Use the official OpenAI Python SDK. The OpenAI documentation confirms that the Responses API
accepts image input and that Structured Outputs constrains output to a JSON schema. Set
`store=False` because this app retains the request and response in its own user-owned row. Use
`gpt-5-mini` as the configurable default because its current model page lists image input and
Structured Outputs. Pin the chosen model name in `OPENAI_FOOD_ANALYSIS_MODEL` so a provider alias
change does not silently alter production behavior. Record the actual response model on each call.

Provider refusal, transport failure, malformed output, and local storage failure map to stable
analysis error codes. Only a confirmed provider call consumes quota. Diagnostics stored in the row
stay short and sanitized. The endpoint never returns provider text or an unvalidated partial item.

## Photo save and object ownership

Extend `FoodEntry` with a nullable `photo_key`. Manual rows remain null. Add a Photo entry request
variant to `POST /api/entries/` rather than creating a screen-named save route. The request carries
the analysis identifier and local-day fields. It does not resend model-produced item values.

The save service locks and scopes the succeeded analysis row to the authenticated user. It rejects
failed analyses and reuse by an existing entry. It then:

1. Copies the single durable analysis object to an entry-owned `entries/{user_id}/...` key.
2. Creates or reads the DailyLog, creates one Photo `FoodEntry`, copies all validated items from the
   retained response, and derives aggregate totals inside one database transaction.
3. Stores the entry key and updates the analysis request snapshot to the same stable key.
4. Deletes the old analysis object after the database commit.

If the database transaction fails after the copy, the service deletes the new copy and leaves the
analysis object for retry. If deletion of the old object fails after commit, both keys temporarily
exist, but the entry key remains valid and a later cleanup can remove the unreferenced analysis
copy. This is a small saga around R2 and Postgres because one transaction cannot cover both systems.

The day response adds a nullable, short-lived `photo_url` derived from `photo_key`. It never exposes
the stable key. Today can show a thumbnail for Photo entries now. Entry detail remains outside this
ticket.

## Files and contract changes

Backend changes affect:

- `apps/api/ai/`: provider adapter, analysis serializers, service, view, URL, error mapping, and
  focused tests.
- `apps/api/uploads/services.py`: analysis-key promotion and entry-key transfer helpers with
  idempotent copy and cleanup behavior.
- `apps/api/entries/`: `photo_key`, migration, Photo save serializer/service, response photo URL,
  endpoint tests, and cross-user protections.
- `apps/api/config/urls.py` and settings: analysis route and OpenAI model/cost configuration.
- `.env.example`, `apps/api/pyproject.toml`, and `apps/api/uv.lock`: provider configuration and SDK.
- `packages/api-client/`: regenerated OpenAPI schema, endpoint functions, and request, response,
  quota, and failure types. Generated files are never hand-edited.

Mobile changes affect:

- `apps/mobile/app/(app)/log-food.tsx`: working Photo choice while preserving Manual.
- New Photo capture and Review routes under `apps/mobile/app/(app)/`.
- A small `apps/mobile/lib/photo-analysis.ts` orchestration module for compression, upload,
  analysis, error classification, and save.
- App configuration, package metadata, and mobile tests for the two Expo image modules.

The entry migration is additive and needs no backfill. Existing Manual rows get a null photo key.
The analysis endpoint and Photo request variant change OpenAPI, so this PR regenerates the client.

## Django and React Native concepts

- The provider adapter is a dependency boundary. Tests substitute it without mocking the analysis
  rules or accounting service.
- DRF serializers validate both the public request and the provider result. Structured Outputs
  reduce malformed responses, but server validation remains the trust boundary.
- `transaction.atomic`, row locks, and `transaction.on_commit` coordinate database state. The R2
  transfer uses compensation because an object store cannot join a database transaction.
- Expo permission APIs represent `granted`, `denied`, and restricted access explicitly.
- The screen uses a finite set of capture, working, review, and error states. It keeps user input in
  the route that owns the flow instead of global application state.
- React Query invalidation makes Today reread server state after save.

## Tests and acceptance

Backend tests cover:

- authenticated analysis, optional and present descriptions, prompt input, strict provider schema,
  validated multiple items, derived totals, usage, cost, and succeeded call accounting;
- invalid provider JSON, refusal, timeout, pre-dispatch storage failure, billable provider failure,
  sanitized diagnostics, and absence of unvalidated output;
- quota rejection shape, status, retry timestamp, no provider call, and no extra attempt row;
- pending-key ownership, analysis-key retention after analysis without save, and no stored image
  bytes or presigned URL;
- Photo save with multiple items, captured targets, local date and timezone rules, one-time analysis
  use, cross-user isolation, object transfer, compensation, and Manual behavior unchanged;
- day reads with and without a Photo entry and a presigned download URL;
- migration state, OpenAPI examples, and generated-client drift.

Mobile tests cover:

- Photo and Manual navigation from both logging entry points;
- camera granted and denied states, Library fallback, and Settings action;
- compression arguments, presign request metadata, direct upload headers, optional description,
  analysis request, and both inputs reaching the same Review screen;
- Review totals and item rows, successful save, Today query invalidation, and navigation;
- retained photo and description after upload or analysis failure;
- retry with a new upload, Manual fallback, typed quota copy, and prevention of duplicate taps.

Run the focused API and mobile suites first. Then run the full backend suite, Ruff, Ruff format,
mypy, migration drift, schema generation, generated-client drift, TypeScript, ESLint, Prettier, the
full mobile Jest suite, and `git diff --check`.

The physical-device acceptance path uses a nonpersonal test meal photo. It proves Camera and
Library permissions, image orientation and compression, direct R2 upload, real provider analysis,
Review, save, Today refresh, and durable R2 retrieval. The PR includes live captures of the Photo
input, permission failure, working, retryable failure, quota, Review, and saved Today states.

## Alternatives rejected

- Sending image bytes through Django ties up an app worker and duplicates the existing presigned
  upload path.
- Passing model item values back into the save request lets a client bypass the validated analysis
  and makes the analysis identifier meaningless.
- Trusting Structured Outputs without local validation makes a provider feature the database trust
  boundary.
- Keeping analyzed but unsaved images under `pending/` lets lifecycle cleanup destroy the input for
  retained analysis records.
- Copying every analyzed image permanently into both `analyses/` and `entries/` contradicts the
  single-object retention decision and doubles photo storage.
- Holding a database transaction open across R2 or OpenAI network calls increases lock time and
  cannot make those external effects atomic.
- Adding item editing now duplicates MAC-57 and makes this already wide provider slice harder to
  review.
- Adding background jobs or offline queuing changes the product promise and is outside MVP scope.

## Blast radius and deliberately unhandled work

This ticket adds native permissions, two mobile screens, one public analysis resource, one entry
request variant, a nullable database field, provider traffic, and durable object movement. It can
affect R2 cost, OpenAI cost, entry creation, and Today response latency. The rolling quota, strict
validation, short signed URLs, ownership checks, and focused transaction tests bound those risks.

MAC-57 owns correction before and after save. Later tickets own Recents, entry detail, delete and
edit, past-day selection, offline work, multiple photos, background analysis, confidence editing,
and cleanup or reconciliation jobs. This ticket does not add a reusable upload queue or retain
device photos outside the open flow.

## Approval gate

Implementation starts after Alex approves this plan. Approval includes these choices: use the
OpenAI Responses API with configurable `gpt-5-mini`, retain analyzed unsaved photos under an
analysis key, move the single object to an entry-owned key on save, make Review read-only until
MAC-57, and return a short-lived photo URL from the existing day resource.
