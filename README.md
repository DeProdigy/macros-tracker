# Macros Tracker

[![CI](https://github.com/DeProdigy/macros-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/DeProdigy/macros-tracker/actions/workflows/ci.yml)

A photo-based macro tracker.

Take a photo of your food and add a short description. An AI estimates the
calories, protein, and fiber. The entry is saved against your daily targets.
A home dashboard shows the day, and an on-demand suggestion answers "what should
I eat?".

This is a **learning project**, levelling up React Native and Django end to end.
The full plan lives in [`plans/`](./plans). Start with
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

One architectural decision shapes the rest: the API contract is generated, not
written twice.

```
Django serializers → drf-spectacular → openapi.json → Orval → typed React Query hooks
```

The mobile app calls those hooks. Nobody hand-writes a request type. See
[`plans/01-architecture-and-repo-structure.md`](./plans/01-architecture-and-repo-structure.md).

## Prerequisites

- **Node**, at the version pinned in [`.nvmrc`](./.nvmrc), currently Node 22 LTS.
  Use [nvm](https://github.com/nvm-sh/nvm), not Homebrew. Homebrew's Node fights
  your PATH.
  ```bash
  nvm install   # reads .nvmrc
  nvm use
  ```
- **pnpm**, managed by Corepack. The `packageManager` field in `package.json`
  pins the version, so there is nothing separate to install.
  ```bash
  corepack enable
  ```
- **git**, and the **GitHub CLI** (`gh`) for repo and CI tasks.

The backend needs two more things: **Python 3.12+** through
[uv](https://docs.astral.sh/uv/), and **Docker** to run its Postgres database.
[`apps/api/README.md`](./apps/api/README.md) has the backend quickstart.

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
| `pnpm test`         | Run **JS** test suites (mobile jest)     |
| `pnpm format`       | Format with Prettier                     |
| `pnpm format:check` | Check formatting without writing         |

## Testing

There are two test suites, run separately:

| Suite                    | Where         | Command                    | Notes                                             |
| ------------------------ | ------------- | -------------------------- | ------------------------------------------------- |
| **Mobile** (Jest + RNTL) | `apps/mobile` | `pnpm test` (or from root) | runs in Node, no Metro/device needed              |
| **Backend** (pytest)     | `apps/api`    | `uv run pytest`            | needs Docker Postgres up (`docker compose up -d`) |

Root-level `pnpm test` covers the **JS** packages only (turbo doesn't run the
Python suite — the Django app isn't a pnpm workspace). So "everything" is:

```bash
pnpm test                       # mobile
(cd apps/api && uv run pytest)  # backend
```

See [`apps/mobile/README.md`](./apps/mobile/README.md) and
[`apps/api/README.md`](./apps/api/README.md) for per-app details.

## Tooling notes

- **pnpm** over npm/yarn: best Turborepo workspace handling, and strict about
  phantom dependencies.
- If `pnpm install` rejects a just-published package on a
  `minimumReleaseAge` supply-chain check, the dependency is newer than the
  policy window — pin the previous, aged release rather than disabling the guard.
- Everything under `packages/api-client/src` is generated output. Never edit it
  by hand; regenerate it after any API change.
