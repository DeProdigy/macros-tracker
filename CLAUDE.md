# CLAUDE.md

Planning source of truth is the Linear project. [`plans/`](./plans) is a
**generated mirror** of it — never hand-edit anything in there except
`plans/tickets/`. To change a plan, edit the Linear doc and run
`pnpm sync:plans`. Feed the relevant plan doc into a session rather than
re-explaining decisions.

Start at [`plans/README.md`](./plans/README.md), which indexes every doc and
says which one wins in a conflict. Architecture is in
[`plans/01-architecture-and-repo-structure.md`](./plans/01-architecture-and-repo-structure.md);
the working agreement this file enforces is in
[`plans/03-working-agreement-and-ai-workflow.md`](./plans/03-working-agreement-and-ai-workflow.md).

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

## Layout

pnpm + turbo monorepo (`pnpm@11.15.1`), workspaces `apps/*` and `packages/*`:

| Path | What |
| -- | -- |
| `apps/api` | Django 6 + DRF, Python 3.12, dependencies managed with `uv` |
| `apps/mobile` | Expo SDK 57 + expo-router, React Native 0.86, TypeScript |
| `packages/api-client` | **Generated** TypeScript client (drf-spectacular → Orval). Never hand-edit |
| `plans` | **Generated** mirror of the Linear docs (`pnpm sync:plans`). Never hand-edit, except `plans/tickets/` |

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
