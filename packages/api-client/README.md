# @macros/api-client

Typed client for the Macros Tracker API. Consumed by `apps/mobile`, and by any
web client added later.

## ⚠️ `src/` and `openapi.json` are generated — do not hand-edit

Everything under `src/`, plus `openapi.json`, is build output. Edits there are
silently destroyed on the next generation run (`clean` wipes `src/` entirely).
The root ESLint and Prettier configs ignore `src/` for the same reason.

Only three files in this package are hand-written:

| File              | Purpose                                      |
| ----------------- | -------------------------------------------- |
| `index.ts`        | Public barrel — what consumers import        |
| `http-client.ts`  | Fetch mutator: base URL, headers, `ApiError` |
| `orval.config.ts` | Generation settings                          |

## Regenerating

From the repo root, after any API change:

```bash
pnpm generate:api
```

That runs two steps in order, wired through Turborepo:

1. `apps/api` — `manage.py spectacular` re-emits `openapi.json` from the Django
   serializers and views.
2. `packages/api-client` — Orval turns that schema into React Query hooks and
   TypeScript types.

The output is committed on purpose. Generated code in the diff is what makes an
API change visible during review, and it's what MAC-16's CI drift check compares
against.

## Why this exists

Rename a field in a Django serializer, regenerate, and `pnpm check-types` fails
in `apps/mobile` at the exact call site — at build time, rather than returning
`undefined` to a user in TestFlight. That failure is the feature.

Hook names come from the `operationId` set explicitly via `@extend_schema` in
Django. Without it you get names like `useApiV1PingRetrieve`, and changing them
later churns every call site.
