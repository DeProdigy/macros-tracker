import { defineConfig } from "orval";

/**
 * Generates typed React Query hooks from the Django-emitted OpenAPI schema.
 *
 * Input  : openapi.json  (written by `manage.py spectacular`, see apps/api)
 * Output : src/          (never hand-edited — `clean` wipes it every run)
 *
 * Everything under src/ is build output; the root ESLint and Prettier configs
 * ignore it on that basis. Hand-written files (http-client.ts, index.ts) sit at
 * the package root so regeneration can't delete them and linting still covers
 * them.
 */
export default defineConfig({
  macros: {
    input: {
      target: "./openapi.json",
    },
    output: {
      // Endpoints in one module, schemas split per type. Keeps the package's
      // public surface a stable barrel — a per-tag layout would need a new
      // export line in index.ts every time a Django app adds a tag.
      mode: "split",
      target: "./src/endpoints.ts",
      schemas: "./src/model",
      client: "react-query",
      httpClient: "fetch",
      // Wipe stale operations: a deleted endpoint must vanish from the client,
      // not linger as a hook that compiles and 404s.
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: "./http-client.ts",
          name: "customFetch",
        },
      },
    },
  },
});
