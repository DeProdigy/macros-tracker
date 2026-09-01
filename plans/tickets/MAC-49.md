# MAC-49 implementation plan

Approved 31 Aug 2026.

## User outcome

A user is protected from unbounded photo-analysis cost before photo logging ships.

## Horizontal safety control

This ticket deliberately has no user-visible happy path. MAC-54 owns the photo-analysis
endpoint and mobile flow, but it must not make a paid provider call until accounting and a
concurrency-safe server limit exist. MAC-49 supplies that boundary without adding a placeholder
endpoint or coupling the records to Manual and Recent logging.

## Canonical sources and current behavior

- `plans/start-here-product-scope-and-sources-of-truth.md` limits AI use here to itemized food
  estimates; deterministic targets, Manual, and Recent do not call a model.
- `plans/canonical-engineering-baseline-and-mvp-architecture.md` requires one record per analysis
  attempt and derives the rolling quota from those rows rather than a second counter.
- `plans/canonical-mvp-experience-and-screen-flows.md` requires a clear quota state in the future
  Photo flow; it does not promise offline work or a billing workflow.
- `plans/canonical-mvp-visual-design-and-approved-screens.md` lists quota reached as a required
  Photo-analysis state, but no approved UI export exists and this ticket changes no UI.
- The MVP 2 milestone makes AI-call accounting and quota protection prerequisites of the photo
  slice. MAC-55 has supplied the food domain, while MAC-54 will supply the provider integration,
  endpoint, generated client contract, and mobile presentation.
- The repository currently has an empty `ai` package and no provider client or analysis endpoint.
  Manual entry writes only `DailyLog`, `FoodEntry`, and `FoodItem`.

## Data model

Turn `apps/api/ai` into a Django app and add `FoodAnalysisCall`, owned by a user, with:

- a lifecycle status of `reserved`, `succeeded`, or `failed`;
- `created_at`, `started_at`, and nullable `completed_at` timestamps;
- nullable measured latency in milliseconds;
- provider, model, and nullable provider response/request identifier;
- nullable input tokens, output tokens, and provider-specific usage metadata;
- nullable estimated cost in USD using a decimal field;
- nullable failure category and a short sanitized diagnostic message;
- the food-analysis request as structured JSON, including the description and durable R2 object
  key but never image bytes or a presigned URL;
- the raw provider response as JSON when the provider returns parseable JSON, plus a raw text field
  for a malformed response that failed structured validation.

The request and response snapshot is intentional product data, not logging exhaust: it preserves
the input and output needed to inspect mistakes, learn from past analyses, or build a future
training/evaluation dataset. The snapshot may contain personal meal data and therefore follows the
user row's deletion lifecycle. The image itself remains a single object in R2; this row stores only
its stable object key. MAC-54 must promote analyzed images needed by retained call records out of
the pending-upload namespace even when the user does not save the proposed entry, otherwise a
cleanup job could silently destroy the input half of this dataset. That retention behavior and any
future training consent/export policy must be explicit in MAC-54; MAC-49 establishes the fields but
has no image object to retain yet.

Use normal user-cascade deletion, timestamps indexed for the rolling query, and an index beginning
with user and creation time. Register the model read-only in Django admin so individual rows are
inspectable for operations without creating an analytics dashboard or allowing history edits.

## Quota reservation and call lifecycle

Add a food-analysis accounting service with separate reserve and finalize operations:

1. Start a database transaction and lock the authenticated `User` row with
   `select_for_update()`. The user row is the stable lock even when that user has no prior calls.
2. Count calls whose provider result confirms paid work and whose quota-debit time is at or after
   the exact UTC instant 30 days earlier, plus live reservations that could become paid calls. A
   local validation, setup, or unbilled provider failure does not consume one of the 500 calls.
3. If the configured limit is exhausted, raise `FoodAnalysisQuotaExceeded` without inserting a row.
   The exception carries machine-readable code, limit, usage, window length, and the earliest
   retry timestamp derived from the oldest counted row.
4. Otherwise insert a `reserved` row inside the same transaction. Concurrent requests for one user
   serialize on the user lock, so they cannot both observe the final slot as free.
5. Release the transaction before external network work. Immediately before provider dispatch,
   stamp `provider_called_at`. MAC-54 will then finalize the row as succeeded or failed, record its
   retained request, response, usage, and cost, and stamp `quota_debited_at` only when the provider
   result represents work that is charged against the paid API allowance.

Do not hold a database transaction open across a provider request. A live `reserved` row occupies
a slot so concurrent requests cannot oversubscribe the limit. A reservation that fails before
dispatch is finalized as failed with no `provider_called_at` and no longer counts. A process crash
can leave a reservation behind, so reservations expire from quota occupancy after a short,
configured safety timeout; the audit row remains. A crash after dispatch is temporarily
conservative, then releases the reservation because the app has no provider result proving that it
was paid. Provider reconciliation can mark such a row billable later if MAC-54's chosen API exposes
that capability.

Expose a small context/helper API that guarantees ordinary provider exceptions mark an admitted
row failed before re-raising. Keep reservation explicit so a quota rejection itself creates no
attempt row: no provider call was admitted or made.

## Typed error and API boundary

Define the domain exception and a DRF error serializer/schema with a stable code such as
`food_analysis_quota_exceeded`. MAC-54 will map that exception from its analysis endpoint and add
the response to OpenAPI; MAC-49 will not invent an otherwise unusable quota-check endpoint solely
to generate a client type. This keeps the concurrency control independently testable while making
the eventual HTTP contract explicit.

There is no generated-client change in this ticket because no public route changes. The MAC-54 PR
must regenerate the client when it adds the analysis route and typed error response.

## Configuration

Set the rolling limit to 500 paid food-analysis API calls in the previous 30 days. Read it from a
production setting with a default of 500, document the environment variable in `.env.example`, and
validate that it is positive at startup. Also configure the short reservation timeout used only to
recover capacity from a process that dies before provider dispatch. The database rows remain the
only usage source of truth; configuration sets the admission ceiling and does not create a mutable
monthly counter.

## Tests

Backend model and service tests will cover:

- a successful call moving from reserved to succeeded with timestamps, usage, latency, model
  metadata, and estimated cost;
- a provider failure moving the row to failed while preserving the original exception;
- the exact 30-day boundary with a controllable clock;
- quota rejection returning the typed values and creating no extra row;
- two real concurrent database transactions competing for the last slot, with exactly one
  reservation admitted;
- rolling usage including live reservations and succeeded or failed calls that crossed the provider
  boundary, while excluding local pre-dispatch failures and expired reservations;
- different users not sharing a quota or lock;
- Manual entry creating no AI-call row (Recent has no implementation yet, so its future service
  must remain outside this API);
- retained request/response snapshots, absence of duplicated image bytes and presigned URLs, and
  cascade deletion with the user;
- migration state, admin read-only behavior, and settings validation.

Use PostgreSQL transaction tests for concurrency rather than mocks: `select_for_update()` behavior
cannot be established by asserting that a method was called. Run the focused AI and entry tests,
then the complete backend suite, Ruff, Ruff format, mypy, migration drift, schema generation/drift,
and `git diff --check`.

## Alternatives rejected

- A per-user monthly counter can drift from call history and resets on calendar boundaries rather
  than using the previous 30 days.
- Cache throttling is process-local in this repository and is neither durable nor concurrency-safe
  across workers.
- Counting and inserting without a stable row lock permits two requests to consume the final slot.
- Holding the user lock during the model request makes unrelated attempts wait on network latency
  and leaves a long-running transaction.
- Storing image bytes or presigned URLs in Postgres duplicates large sensitive content or preserves
  an expiring credential; a stable R2 key plus the structured request and response preserves the
  future learning dataset without either problem.
- A quota-only public endpoint would expose a check-then-act race and would exist only until MAC-54
  adds the real analysis endpoint.

## Blast radius and deployment

This adds one Django app, one table and migration, settings/environment documentation, admin
registration, and backend-only accounting services. It does not call a model, add a dependency on a
provider SDK, change the OpenAPI contract, alter Manual logging, implement Recent, or change UI.
The migration is additive and needs no data backfill.

## Approval gate

Alex chose a limit of 500 paid provider calls per rolling 30 days. Only provider-confirmed paid work
consumes the quota; live reservations occupy capacity solely to prevent a concurrent
oversubscription. Request and response snapshots are retained deliberately for future learning,
evaluation, or training, with the analyzed image referenced once in R2.

Implementation starts after Alex approves this revised plan.
