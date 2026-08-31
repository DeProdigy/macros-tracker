# CLAUDE.md

Planning source of truth is the Linear project. [`plans/`](./plans) is a
**generated mirror** of it. Never hand-edit anything there except
`plans/tickets/`. To change a plan, edit Linear and run `pnpm sync:plans`.

Start at [`plans/README.md`](./plans/README.md). Only documents whose titles
start with `START HERE` or `CANONICAL` define current requirements. Alex is the
final source of truth for clarification. Active milestones and issues apply
after the canonical documents.

Never use a document or mirror file marked `ARCHIVED` to plan or implement
work. Archived files preserve history and can contain detailed requirements
that were reversed. The Decision Log is historical reasoning, not a spec.

---

## How to work on this repo

This is a learning project. The owner is levelling up React Native and Django
by reviewing plans and code rather than writing it.

For every ticket:
- Produce a full implementation plan BEFORE writing code
- Plan must cover: files touched, approach, alternatives rejected,
  Django/RN concepts in play, blast radius, what's deliberately unhandled,
  and open questions
- Wait for plan approval before implementing
- Save the approved plan to `plans/tickets/MAC-NN.md` and commit it
- In the PR description, call out anything the owner should look at closely
  and anything you were unsure about

When asked "why", explain the concept, not just this instance. Name the
pattern. Say when it's the wrong choice.

The `you-implement` and `auto-ok` labels are **retired** (doc 03, 19 Aug 2026).
Existing tickets still carry them; ignore them. Every ticket now gets the plan
gate above and a full diff review before merge. The per-language rules that used
to sit here are the sections below.

## Slice epics vertically

An epic is cut into tickets that each go **through every layer**, from the
database to a screen someone can tap. The opposite is layering: all the models,
then all the endpoints, then all the screens. Layering is the default this repo
keeps drifting into, so it needs a rule.

The agile name for the test is **INVEST** (Bill Wake, 2003). A story should be
Independent, Negotiable, **Valuable**, Estimable, Small, and Testable. Valuable
is the one that forces the slice: value means value to a person using the app,
not to the developer building it.

E1 already worked this way. Doc 09 calls it "deploy early, deploy always", and a
walking skeleton (Alistair Cockburn's term) is a vertical slice at epic scale.

### Why it matters here, and it is not the usual reason

Vertical slices usually pay off through early user feedback. This project has no
users yet, so that argument does not apply.

The payoff here is **risk order**. Layering builds the safe parts first and the
dangerous part last. E3 as first planned put the AI call fourth: the only piece
that talks to an outside service, the only one that can return garbage, the only
one with no precedent in this repo. A vertical cut ships a working product
before that risk arrives, so a bad answer costs a slice instead of an epic.

### How to cut one

Pick the thinnest thing a person can do end to end. Then take these in order:

1. **Happy path first.** Defer the error states, the empty states, and the
   variations
2. **One rule at a time.** Ship the calculation without the special cases
3. **Manual before automatic.** A user typing the value is a real product. The
   computed version is the next slice
4. **Deterministic before AI.** The formula alone is shippable. Doc 18 already
   says so: the fallback numbers "are sound"

Each slice should end with a sentence starting "a user can now...". If you cannot
write that sentence, it is not a slice.

### When a horizontal ticket is right

These are allowed. Say which one applies, in the plan.

- **No user-visible face exists yet.** A custom user model, a `TargetVersion`
  table. Forcing these into a slice invents a screen nobody asked for
- **The generated client makes thin slices expensive.** Every API change costs a
  `pnpm generate:api`, a committed diff, and a drift check. Batching two or three
  related endpoints into one ticket is often cheaper than three slices
- **The plan gate makes tickets expensive.** Every ticket needs a written plan
  and a review before code. Small stories are nearly free on a team. They are not
  free here
- **A safety control has to land before the thing it guards.** The clamp ships
  before the AI call that needs clamping. Order by danger, not by demo value

The exception is the reason to write one sentence, not the reason to skip the
question.

## How to write

Everything written here follows **ASD-STE100 Simplified Technical English**.
That is the controlled language aircraft maintenance manuals use. Its rules stop
a tired reader misreading an instruction.

This covers READMEs, code comments, docstrings, `plans/tickets/`, commit
messages, and PR descriptions. It covers user-facing copy too.

### The sentence rules, everywhere

- **Active voice.** Name who acts. "The compiler validates queries", not
  "queries are validated"
- **One idea per sentence.** If you need a comma to bolt on a second thought,
  make it a second sentence
- **Plain words.** "use", not "utilize". "help", not "facilitate". "many", not
  "numerous". If a technical term is the accurate word, keep it and explain it
  once
- **Short paragraphs.** Three or four sentences
- **Present tense.** "The clamp rejects the value", not "the clamp will reject"
- **No em dashes.** Use a period or a comma

### Length is not the same rule

Simple sentences do not mean thin content. These two need different amounts of
text and the difference is deliberate.

**READMEs and runbooks say only what to do.** Exact commands, exact paths, the
order to run them. Cut everything else. Someone reads these while something is
broken.

**Code comments and plan docs explain why, at whatever length that takes.** This
is a learning project. A comment that names the pattern, says what was rejected,
and says when the choice would be wrong is the deliverable, not decoration.
Write those long thoughts in short sentences.

The test for a comment: it should say something the code cannot. A comment that
restates the line above it is noise at any reading level.

### What not to write

- Filler. "It is important to note that", "in order to", "due to the fact that"
- Puffery. "load-bearing", "robust", "seamless", "powerful"
- Metaphor nouns where a plain one exists. "substrate" is "base". "surface" is
  "the set of endpoints"
- Bold on every proper noun
- Emoji in headings

## Layout

pnpm + turbo monorepo (`pnpm@11.15.1`), workspaces `apps/*` and `packages/*`:

| Path | What |
| -- | -- |
| `apps/api` | Django 6 + DRF, Python 3.12, dependencies managed with `uv` |
| `apps/mobile` | Expo SDK 57 + expo-router, React Native 0.86, TypeScript |
| `packages/api-client` | **Generated** TypeScript client (drf-spectacular → Orval). Never hand-edit |
| `plans` | **Generated** mirror of Linear. Read only START HERE and CANONICAL docs. Never hand-edit, except `plans/tickets/` |

Django apps: `accounts` (custom User model), `uploads` (Cloudflare R2 presigned
uploads). `entries`, `targets`, and `ai` are scaffolded but still empty.

## Commands

Run from the repo root — turbo fans out to the workspaces.

- `pnpm lint`, `pnpm format:check`, `pnpm check-types`, `pnpm test`
- `pnpm generate:api` — regenerate the API client (deliberately never cached)
- `pnpm sync:plans` — re-mirror the Linear plan docs into `plans/`. Needs
  `LINEAR_API_KEY` in `.env`. Run it at the start of an epic, and any time a
  plan doc changes in Linear
- Python, from `apps/api`: `uv sync --all-groups`, `uv run ruff check .`,
  `uv run mypy`, `uv run pytest`
- Use `uv` and `pnpm` — never bare `pip` or `npm install`; they own the lockfiles

## The api-client contract

`packages/api-client` is generated from the DRF schema, and CI has a dedicated
`api-client-drift` job that regenerates it and fails if the result differs from
what is committed.

- Any API change → run `pnpm generate:api` and commit the result in the same PR
- Schema generation runs `spectacular --fail-on-warn`, so an unannotated view
  fails generation before drift is even computed

## Django conventions

- Explicit DRF serializers, never `fields = "__all__"`
- Business logic in `services.py`, thin views (see `apps/api/uploads/services.py`)
- Every new view or endpoint MUST carry `@extend_schema` with a description,
  parameters, and examples — this is what keeps `--fail-on-warn` green
- Every new feature ships with unit tests covering the edge cases
- ruff (line length 100; `E,F,I,UP,B,DJ`) and mypy both gate CI

## REST route conventions

**A URL names a resource. The HTTP method supplies the verb.** Every route added
to this API is checked against that sentence before it is written. The 20 Aug
2026 audit rewrote eight of twelve routes because it had not been; see the
Decision Log for the reasoning on each.

Before adding a route, in order:

1. **Name the noun the request acts on.** If the only name that fits is a verb
   (`presign`, `analyze`, `logout`, `sync`), the resource has not been found yet.
   Keep looking — it is usually the thing the call produces
2. **Pick the method for the effect**, not for convenience. `POST` creates,
   `GET` reads and never mutates, `PATCH` partially updates, `DELETE` removes.
   `PUT` is rarely right here: clients send the fields they changed, and a
   full-representation replace cannot tell an omitted field from a cleared one
3. **Return the status the method implies** — `201` when the POST created
   something addressable, `200` when it returns a computed representation that
   has no URL of its own (`/api/uploads/`, `/api/analyses/`), `204` from a
   delete, `200` from a read
4. **Filtering, sorting, and pagination go in the query string**, never in the
   path. `?ordering=`, `?logged_since=`, `?page=` — not `/recent/`, `/history/`,
   `/latest/`

Hard rules that follow from that:

- **Never name a route after the screen that calls it.** `/api/onboarding/…`,
  `/api/foods/recent/`, and `/api/targets/history/` all died in the audit. The
  second caller is what exposes the mistake, and by then the name is in the
  generated client
- **One entity gets one URL.** If two paths address the same row, the design is
  wrong regardless of how different the operations feel. `GET /api/auth/me/`
  plus `DELETE /api/auth/account/` was the clearest example
- **The URL tree and the Django app tree are allowed to differ.** `entries` owns
  `/api/analyses/`; `accounts` owns both `/api/auth/` and `/api/users/`. Forcing
  them to match is what produced `/api/entries/analyze/`
- **An expensive computation is a resource you create.** `POST /api/analyses/`,
  `POST /api/targets/proposals/`. Whether the result is persisted is an
  implementation detail the URL must not encode

Legitimate exceptions, which are allowed but must be justified in the plan and
in the view's `@extend_schema` description:

- **Named singletons** for a member the client cannot address by id:
  `/api/users/me/`, `/api/targets/current/`. Only when the server genuinely owns
  that state — `/api/days/today/` was rejected because it does not. Route the
  literal before the detail route, and give the detail route a typed converter
  (`<int:pk>`) so the two cannot collide
- **Token exchange** (`POST /api/auth/sessions/refresh/`) is the one place a verb
  survives, because the credential presented is not the resource addressed.
  OAuth 2 landed on the same shape
- **Operational probes** (`/api/ping/`, `/api/health/`) are not resources and are
  out of scope for all of this

Renaming a route is never free after it ships: it changes `openapi.json`, the
generated client, and every call site. Get it right in the plan, where it costs
nothing.

## Mobile conventions

- TypeScript strict; no `any` without a comment justifying it
- Tests are jest + jest-expo

## Git and deploys

- Branches `ahint/mac-NN-slug`; commits and PR titles lead with the ticket
  (`MAC-19: ...`)
- Everything lands through a PR — CI runs the `python`, `node`, and
  `api-client-drift` jobs
- Merging to `main` auto-deploys the API to Railway

## Secrets

Local secrets live in `.env`; deployed ones are Railway variables.
