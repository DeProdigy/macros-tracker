# 01 — Architecture & Repo Structure

## Monorepo layout

Turborepo, single repo, three packages.

```
macros-tracker/
├── apps/
│   ├── api/                  # Django project
│   │   ├── config/           # settings, urls, wsgi/asgi
│   │   ├── accounts/         # custom user, auth
│   │   ├── targets/          # TargetVersion, onboarding
│   │   ├── logging/          # DailyLog, FoodEntry
│   │   ├── ai/               # OpenAI client wrappers, prompts
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   └── mobile/               # Expo app
│       ├── app/              # expo-router screens
│       ├── components/
│       ├── hooks/
│       ├── lib/
│       └── app.json
├── packages/
│   └── api-client/           # generated, do not hand-edit
│       ├── openapi.json      # emitted by drf-spectacular
│       ├── orval.config.ts
│       └── src/              # generated React Query hooks + types
├── plans/                    # these documents, mirrored into the repo
├── .github/workflows/
├── turbo.json
└── package.json
```

**Why monorepo:** the API contract and its consumer change together. Separate repos mean version skew and a second PR every time a field name changes.

## The typed API contract

This is the load-bearing architectural decision. The chain:

```
Django serializers/views
  → drf-spectacular introspects
    → packages/api-client/openapi.json
      → Orval generates
        → typed React Query hooks + TS types
          → consumed by apps/mobile
```

Rules:

* **Nothing in** `packages/api-client/src` **is hand-edited.** It is build output.
* Regenerating is a single command, run whenever the API changes.
* CI regenerates and fails the build if the committed output differs. This is the drift guard — without it the whole scheme quietly rots.

**What this buys:** rename a serializer field and the mobile app fails to typecheck immediately, at build time, instead of returning `undefined` at runtime in TestFlight. It also makes adding a web client (TanStack Start) nearly free later, since it consumes the same package.

**What it costs:** one more build step, and a discipline requirement to regenerate before pushing. Worth it.

## Backend shape

* **DRF with explicit serializers.** No `ModelSerializer(fields = "__all__")` — being explicit is what makes the generated schema trustworthy.
* **Apps split by domain**, not by layer. `accounts`, `targets`, `logging`, `ai`.
* **The** `ai` **app owns every OpenAI call.** Prompts live in version-controlled Python modules, not scattered inline strings. One place to change a prompt, one place to mock in tests.
* **Service functions over fat views.** Business logic in `services.py` per app; views stay thin and mostly do serialization and permission checks. Keeps logic testable without HTTP.

## Mobile shape

* **expo-router** for file-based navigation
* **React Query** for all server state, via the generated hooks. No Redux
* **Local UI state** with `useState`/`useReducer`; no global store unless something genuinely demands it
* **TypeScript strict mode** on from day one — retrofitting is miserable
* **expo-secure-store** for tokens, never AsyncStorage

## Environments

| Env | Where | Purpose |
| -- | -- | -- |
| Local | Docker Compose (Postgres) + `runserver` + Expo Go | Day-to-day dev |
| Production | Railway (Django + Postgres), R2 bucket | TestFlight and beyond |

No staging environment in v1. One backend, one database. A solo project with a staging tier spends more time on env parity than on features. Revisit if/when there are real users.

## CI pipeline (GitHub Actions)

On every PR:

1. Lint — ruff (Python), eslint + prettier (TS)
2. Typecheck — mypy (Python), tsc (TS)
3. Test — pytest, jest
4. **Regenerate api-client and fail on diff**

On merge to main:
5. Railway auto-deploys the API
6. Migrations run on deploy

Mobile builds are triggered manually via EAS, not on every merge — builds are slow and App Store submissions are deliberate acts.

## Things deliberately not used in v1

* **Celery/Redis.** Photo analysis runs synchronously in the request first. If p95 latency becomes a real problem, that's an informed reason to add a queue — adding it preemptively is complexity without evidence. Tracked as a spike.
* **GraphQL.** REST + generated types already solves the typing problem.
* **Kubernetes, Terraform.** Railway's abstraction is the right level for one developer.
