# Mobile (Expo)

The React Native app — Expo (managed workflow), **expo-router** for file-based
navigation, TypeScript strict. Talks to the Django API in `apps/api`.

On **Expo SDK 57**. Track the latest SDK rather than pinning back to match an
older Expo Go: iOS Expo Go runs only the newest SDK, so the project and a
current Expo Go stay aligned by both moving forward. MAC-20 replaces Expo Go
with an EAS dev build, which embeds its own runtime and drops the constraint.

## Prerequisites

- **Node** (via [nvm](https://github.com/nvm-sh/nvm)) + **pnpm** (via Corepack) — see the repo root README.
- **[Expo Go](https://expo.dev/go)** installed on your phone (App Store), and
  **up to date** — check the supported SDK under Settings in the app. An older
  Expo Go rejects the project before it loads any JS, which reads like a
  connection failure but is a version mismatch.
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

### Pointing the app at Django from a physical device

`EXPO_PUBLIC_API_URL` defaults to `http://localhost:8000`, which is correct for
the iOS simulator and web, but **wrong on a real phone**: there `localhost` is
the phone itself, not the Mac running Django. The home screen's "API status"
card reads `unreachable` and nothing else explains why.

Set it to your Mac's LAN IP (`ipconfig getifaddr en0`):

```bash
EXPO_PUBLIC_API_URL=http://192.168.1.x:8000 pnpm dev
```

Two things have to agree for that to work:

- Django must listen beyond loopback: `uv run python manage.py runserver 0.0.0.0:8000`.
- That IP must be in `ALLOWED_HOSTS` in `apps/api/config/settings/local.py`,
  which lists only `localhost`, `127.0.0.1` and `0.0.0.0` by default. Django
  answers a missing host with `DisallowedHost`, not a connection error.

## Tests (Jest + React Native Testing Library)

Runs in Node — **no Metro or device needed.**

```bash
pnpm test                 # run once (jest)
pnpm test -- --watch      # re-run on change
pnpm test -- smoke        # only files matching "smoke"
pnpm test -- -t "renders" # only tests whose name matches "renders"
```

Test files live in `__tests__/` (or `*.test.tsx`). The stack is jest-expo 57 +
jest 29 + RNTL 13 + react-test-renderer, matched to Expo SDK 57.

## Lint & types

```bash
pnpm lint           # eslint (inherits the root flat config)
pnpm check-types    # tsc --noEmit
```

All four (`dev`/`lint`/`check-types`/`test`) also run from the repo root via
Turborepo (e.g. `pnpm lint` at the root includes this package).
