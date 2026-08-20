# MAC-33 — REST route audit: make every route resource-shaped

Approved 20 Aug 2026. Linear:
[MAC-33](https://linear.app/hintology/issue/MAC-33/rest-route-audit-make-every-route-resource-shaped).

## The rule this applies

A URL names a resource. The HTTP method supplies the verb.

Twelve routes existed or were planned across the codebase and docs 04–09. Eight
changed. Per-route reasoning lives in each feature doc and in the Decision Log
entry "20 Aug 2026 — REST route audit"; this file records the shape of the work.

## Approach

Nearly all of the surface is unbuilt, so this is mostly a planning change. The
Linear docs are the source of truth (`plans/` is a generated mirror), so every
edit went into Linear and `pnpm sync:plans` regenerated the mirror. One shipped
route was renamed in code.

**Why now rather than later.** E2 is unstarted and the one affected shipped
route has no consumers. After E2 lands, the same rename would touch the mobile
app, the generated client, and every call site. The cost curve here is steep and
one-directional.

## Files touched

| File | What |
| -- | -- |
| Linear docs 04, 05, 06, 07, 08, 09 | Endpoint blocks rewritten, each with the reasoning inline |
| Linear Decision Log | New entry, newest-first at the top |
| `plans/*` | Regenerated — never hand-edited |
| `CLAUDE.md` | New "REST route conventions" section |
| `apps/api/uploads/urls.py` | `presign/` → `` (the collection root) |
| `apps/api/uploads/tests/test_presign.py` | 3 `reverse()` calls, 2 literal schema-path assertions |
| `packages/api-client/*` | Regenerated via `pnpm generate:api` |
| MAC-27, MAC-28, MAC-29 | Re-scoped to the new routes |

## Concepts in play

**Resource modelling for operations that are not CRUD.** `POST /api/analyses/`
and `POST /api/targets/proposals/` are expensive, non-idempotent computations
that persist nothing. The REST answer is to model the *result* as a resource you
create, rather than hanging a verb off a related collection. Whether the server
writes a row is an implementation detail the URL must not encode.

**Named singletons.** `/api/users/me/` and `/api/targets/current/` address a
member the client cannot name by id. Legitimate, with two conditions: the server
must genuinely own that state, and the literal must be routed before the detail
route (`<int:pk>`, typed, so the two cannot collide). `/api/days/today/` failed
the first condition, which is why it was deleted rather than kept.

**The URL tree and the app tree are separate designs.** `entries` will own
`/api/analyses/`; `accounts` will own both `/api/auth/` and `/api/users/`.
Django's `include()` invites you to mirror app names into URL prefixes, and
following that instinct is exactly what produced `/api/entries/analyze/` and put
`me` under `/api/auth/`.

**PATCH over PUT for partial updates.** A full-representation replace cannot
distinguish an omitted field from one the client cleared. Relevant to
`PATCH /api/users/me/` and `PATCH /api/entries/{id}/`.

## Alternatives rejected

**Fold token rotation into `POST /api/auth/sessions/` as a second grant type.**
Purer REST — one resource, one create endpoint, the credential varies. Rejected
because it makes the request body a discriminated union, and Orval generates
those badly enough that every call site pays for the purity.
`POST /api/auth/sessions/refresh/` keeps its verb as a documented exception,
which is the same shape OAuth 2 settled on.

**Rename `POST /api/advice/` to `/api/suggestions/`.** Reads better, describes
the response worse. One POST creates one advice object that holds three
suggestions; a POST to `/api/suggestions/` implies creating one suggestion.

**Change `operation_id="presignUpload"` to `createUpload`.** Operation ids are a
different namespace from URLs. They name operations, and operations are allowed
verbs — `usePresignUpload` tells a reader what comes back, `useCreateUpload`
does not.

**Return `201` from `POST /api/uploads/`.** Nothing addressable was created. The
response is a computed authorisation with no URL of its own, so `200` is
correct. Same reasoning will apply to `/api/analyses/`.

## Blast radius

Small, deliberately. The code change is one route with no consumers: nothing in
`apps/mobile` calls `usePresignUpload` yet. The generated client diff is two
lines. `api-client-drift` in CI is the check that would catch a missed regen.

The larger risk is documentation drift — a stale route surviving in a doc and
being implemented from it later. Mitigated by grepping every plan doc rather
than only the ones with an "Endpoints" heading, which is how the rate-limit
table in doc 09 got caught.

## Deliberately unhandled

- **The single-item re-prompt request shape** (doc 06). Recorded as an open
  question for E4: an optional field on the analysis request keeps the generated
  client simple, a distinct request shape is more honest about the two modes.
  Not decided here because E4 has the context to decide it
- **Pagination and filter parameter names.** The convention says they belong in
  the query string; it does not yet fix the vocabulary. First endpoint that
  needs them sets the pattern
- **`/api/ping/` and `/api/health/`.** Operational probes, not resources.
  Out of scope by design, and noted as such in `CLAUDE.md`

## Open questions

None blocking. The one judgement call worth revisiting if it starts to chafe is
the `sessions/refresh/` exception — if a second grant type ever appears, the
discriminated-union tradeoff should be re-run rather than assumed.
