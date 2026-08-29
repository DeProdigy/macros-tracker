# Mobile (Expo)

The React Native app. Expo managed workflow, **expo-router** for file-based
navigation, TypeScript in strict mode. It talks to the Django API in `apps/api`.

We are on **Expo SDK 57**, and we track the newest SDK rather than pinning back.
The reason is iOS Expo Go: it runs only the newest SDK. If both move forward
together they stay compatible. MAC-20 replaces Expo Go with an EAS dev build,
which carries its own runtime and removes the constraint.

## Prerequisites

- **Node** (via [nvm](https://github.com/nvm-sh/nvm)) + **pnpm** (via Corepack) — see the repo root README.
- **[Expo Go](https://expo.dev/go)** on your phone, from the App Store, and
  **up to date**. Check the supported SDK under Settings in the app.

  An old Expo Go rejects the project before it loads any JavaScript. That looks
  like a connection failure. It is a version mismatch.

- **watchman**, so Metro sees file changes. Install it with
  `brew install watchman`.
- Your phone and your Mac on the **same Wi-Fi**. Metro cannot connect otherwise.

You do **not** need Docker or Postgres for the mobile app. Those are for the
backend.

## Run it

```bash
pnpm install          # from the repo root (installs the whole workspace)
cd apps/mobile
pnpm dev              # start Metro (alias for `expo start`) -> scan the QR with Expo Go
```

You should see the "Macros Tracker" home screen.

Edit files under `app/`. The folder structure is the routing: `app/index.tsx`
becomes `/`, and `app/(auth)/login.tsx` becomes `/login`.

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

Config comes from the environment. Set `EXPO_PUBLIC_API_URL`, and see the
repo-root `.env.example`.

**Never put a secret in an `EXPO_PUBLIC_` variable.** The build copies anything
with that prefix straight into the app bundle, where anyone can read it.

### Pointing the app at Django from a physical device

`EXPO_PUBLIC_API_URL` defaults to `http://localhost:8000`. That is right for the
iOS simulator and for web. It is **wrong on a real phone**.

On the phone, `localhost` means the phone itself, not the Mac running Django. The
home screen's "API status" card reads `unreachable`, and nothing on screen
explains why.

Set it to your Mac's LAN IP (`ipconfig getifaddr en0`):

```bash
EXPO_PUBLIC_API_URL=http://192.168.1.x:8000 pnpm dev
```

Two things have to agree for that to work:

- Django must listen beyond loopback: `uv run python manage.py runserver 0.0.0.0:8000`.
- That IP must be in `ALLOWED_HOSTS` in `apps/api/config/settings/local.py`. By
  default that list holds only `localhost`, `127.0.0.1`, and `0.0.0.0`. Django
  answers a missing host with `DisallowedHost`, not with a connection error.

## Tests (Jest + React Native Testing Library)

These run in Node. You need **no Metro and no device.**

```bash
pnpm test                 # run once (jest)
pnpm test -- --watch      # re-run on change
pnpm test -- smoke        # only files matching "smoke"
pnpm test -- -t "renders" # only tests whose name matches "renders"
```

Test files live in `__tests__/`, or anywhere as `*.test.tsx`. The stack is
jest-expo 57, jest 29, RNTL 13, and react-test-renderer. All four are matched to
Expo SDK 57.

## Lint & types

```bash
pnpm lint           # eslint (inherits the root flat config)
pnpm check-types    # tsc --noEmit
```

All four scripts also run from the repo root through Turborepo. Running
`pnpm lint` at the root includes this package.
