/**
 * @macros/api-client — typed client for the Macros Tracker API.
 *
 * The hooks and types re-exported here are GENERATED from apps/api's OpenAPI
 * schema. Never edit anything under src/: run `pnpm generate:api` from the repo
 * root instead, which re-emits openapi.json from Django and re-runs Orval.
 *
 * This file and http-client.ts are the only hand-written sources in the package.
 */

// Generated React Query hooks for every operation in the schema.
export * from "./src/endpoints";

// Generated request/response types.
export * from "./src/model";

// Hand-written transport layer, exported so callers can catch ApiError.
export { ApiError, customFetch } from "./http-client";
