# Macros Tracker

A photo-based macro tracker. Snap or upload a photo of food, add a short
description, an AI estimates calories / protein / fiber, and the entry persists
against your daily targets — with a home dashboard, streaks, and an on-demand
"what should I eat?" suggestion.

This is a **learning project** (levelling up React Native + Django end to end).
The full plan lives in [`plans/`](./plans); start with
[`plans/00-app-overview.md`](./plans/00-app-overview.md).

## Repo layout

```
macros-tracker/
├── apps/
│   ├── api/          # Django project (added in MAC-13)
│   └── mobile/       # Expo / React Native app
├── packages/
│   └── api-client/   # generated React Query hooks + types — do NOT hand-edit
├── plans/            # mirrors of the Linear project docs
├── turbo.json        # Turborepo task pipeline
└── package.json      # pnpm workspace root
```

The load-bearing architectural decision is the typed API contract:
Django serializers → drf-spectacular → `openapi.json` → Orval → typed React
Query hooks consumed by the mobile app. See
[`plans/01-architecture.md`](./plans/01-architecture.md).

## Prerequisites

- **Node** — the version pinned in [`.nvmrc`](./.nvmrc) (Node 22 LTS). Use
  [nvm](https://github.com/nvm-sh/nvm), not Homebrew, so it doesn't fight your
  PATH:
  ```bash
  nvm install   # reads .nvmrc
  nvm use
  ```
- **pnpm** — managed via Corepack (pinned by the `packageManager` field in
  `package.json`, no separate install needed):
  ```bash
  corepack enable
  ```
- **git** and, for repo/CI tasks, the **GitHub CLI** (`gh`).

The backend (`apps/api`) additionally needs **Python 3.12+** (via [uv](https://docs.astral.sh/uv/))
and **Docker** for its Postgres database — see [`apps/api/README.md`](./apps/api/README.md)
for the backend quickstart (`docker compose up`, migrations, dev server).

## Setup from a clean clone

```bash
git clone git@github.com:DeProdigy/macros-tracker.git
cd macros-tracker
nvm use                 # match the pinned Node version
corepack enable         # activate the pinned pnpm
pnpm install            # install the workspace
cp .env.example .env    # then fill in real values
```

## Common commands

All tasks are orchestrated by Turborepo from the repo root:

| Command             | What it does                             |
| ------------------- | ---------------------------------------- |
| `pnpm build`        | Build all apps and packages              |
| `pnpm dev`          | Run all apps in dev mode                 |
| `pnpm lint`         | ESLint across all packages               |
| `pnpm check-types`  | TypeScript typecheck across all packages |
| `pnpm test`         | Run all test suites                      |
| `pnpm format`       | Format with Prettier                     |
| `pnpm format:check` | Check formatting without writing         |

The repo is a skeleton — most pipelines are wired but have nothing to run until
their apps are scaffolded in later tickets.

## Tooling notes

- **pnpm** over npm/yarn: best Turborepo workspace handling, and strict about
  phantom dependencies.
- If `pnpm install` rejects a just-published package on a
  `minimumReleaseAge` supply-chain check, the dependency is newer than the
  policy window — pin the previous, aged release rather than disabling the guard.
- Everything under `packages/api-client/src` is generated output. Never edit it
  by hand; regenerate it after any API change.
