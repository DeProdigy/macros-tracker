# Mobile (Expo)

The React Native app — Expo (managed workflow), **expo-router** for file-based
navigation, TypeScript strict. Talks to the Django API in `apps/api`.

Pinned to **Expo SDK 56** (the version the App Store Expo Go currently supports;
`create-expo-app` scaffolded SDK 57, which Expo Go rejected).

## Prerequisites

- **Node** (via [nvm](https://github.com/nvm-sh/nvm)) + **pnpm** (via Corepack) — see the repo root README.
- **[Expo Go](https://expo.dev/go)** installed on your phone (App Store).
- **watchman** recommended (`brew install watchman`) so Metro sees file changes.
- Phone and Mac on the **same Wi-Fi** for Metro to connect.

Docker/Postgres are **not** needed for the mobile app (that's the backend).

## Run it

```bash
pnpm install          # from the repo root (installs the whole workspace)
cd apps/mobile
pnpm dev              # start Metro (alias for `expo start`) -> scan the QR with Expo Go
```

You should see the "Macros Tracker" home screen. Edit files under `app/` — routing
is folder structure (`app/index.tsx` -> `/`, `app/(auth)/login.tsx` -> `/login`).

## Layout

```
app/            expo-router routes (_layout, index, (auth)/ group)
components/     shared components
hooks/          shared hooks
lib/            non-UI helpers (query-client.ts = the React Query client)
app.config.ts   dynamic config; reads EXPO_PUBLIC_API_URL into extra.apiUrl
app.json        static Expo config
metro.config.js monorepo module resolution
```

Config comes from the environment: set `EXPO_PUBLIC_API_URL` (see the repo-root
`.env.example`). Anything with the `EXPO_PUBLIC_` prefix is inlined into the app
bundle — **never put a secret there.**

## Tests (Jest + React Native Testing Library)

Runs in Node — **no Metro or device needed.**

```bash
pnpm test                 # run once (jest)
pnpm test -- --watch      # re-run on change
pnpm test -- smoke        # only files matching "smoke"
pnpm test -- -t "renders" # only tests whose name matches "renders"
```

Test files live in `__tests__/` (or `*.test.tsx`). The stack is jest-expo 56 +
jest 29 + RNTL 13 + react-test-renderer, matched to Expo SDK 56.

## Lint & types

```bash
pnpm lint           # eslint (inherits the root flat config)
pnpm check-types    # tsc --noEmit
```

All four (`dev`/`lint`/`check-types`/`test`) also run from the repo root via
Turborepo (e.g. `pnpm lint` at the root includes this package).
