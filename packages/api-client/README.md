# @macros/api-client

Typed client for the Macros Tracker API. `apps/mobile` uses it, and so will any
web client added later.

## `src/` and `openapi.json` are generated. Do not hand-edit them.

Everything under `src/`, plus `openapi.json`, is build output. The next
generation run destroys any edit you make, without a warning. The `clean` step
deletes `src/` outright. The root ESLint and Prettier configs skip `src/` for the
same reason.

Only three files in this package are hand-written:

| File              | Purpose                                      |
| ----------------- | -------------------------------------------- |
| `index.ts`        | What consumers import                        |
| `http-client.ts`  | Base URL, headers, `ApiError`, token refresh |
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

The output is committed on purpose, for two reasons. Generated code in the diff
makes an API change visible during review. And the CI drift check from MAC-16
compares against it.

## Why this exists

Rename a field in a Django serializer and regenerate. `pnpm check-types` then
fails in `apps/mobile`, at the exact call site, at build time.

That failure is the feature. The alternative is the app returning `undefined` to
a user in TestFlight.

Hook names come from the `operationId` you set with `@extend_schema` in Django.
Set it every time. Without it you get names like `useApiV1PingRetrieve`, and
renaming later touches every call site.
