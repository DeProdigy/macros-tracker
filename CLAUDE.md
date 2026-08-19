# CLAUDE.md

Planning source of truth lives in [`plans/`](./plans) — mirrors of the Linear
project docs. Feed the relevant plan doc into a session rather than
re-explaining decisions. Architecture is in
[`plans/01-architecture.md`](./plans/01-architecture.md); the working agreement
this file enforces is in
[`plans/03-working-agreement.md`](./plans/03-working-agreement.md).

---

## How to work on this repo

This is a learning project. The owner is levelling up React Native and Django.

For tickets labeled `you-implement`:
- Do NOT write implementation code unless explicitly asked
- Explain concepts, review code, ask guiding questions, unblock errors
- If asked "how do I do X", answer with the concept and a pointer, not a finished file, unless asked for it

For tickets labeled `auto-ok`:
- Implement freely

## Layout

pnpm + turbo monorepo (`pnpm@11.15.1`), workspaces `apps/*` and `packages/*`:

| Path | What |
| -- | -- |
| `apps/api` | Django 6 + DRF, Python 3.12, dependencies managed with `uv` |
| `apps/mobile` | Expo SDK 57 + expo-router, React Native 0.86, TypeScript |
| `packages/api-client` | **Generated** TypeScript client (drf-spectacular → Orval). Never hand-edit |

Django apps: `accounts` (custom User model), `uploads` (Cloudflare R2 presigned
uploads). `entries`, `targets`, and `ai` are scaffolded but still empty.

## Commands

Run from the repo root — turbo fans out to the workspaces.

- `pnpm lint`, `pnpm format:check`, `pnpm check-types`, `pnpm test`
- `pnpm generate:api` — regenerate the API client (deliberately never cached)
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
