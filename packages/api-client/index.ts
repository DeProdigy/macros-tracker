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

// Hand-written transport layer. `configureSession` is how the app hands this
// package its Keychain and its refresh call — see SessionBridge for why the
// dependency points that way.
export { ApiError, ApiTimeout, configureSession, customFetch } from "./http-client";
export type { RefreshOutcome } from "./http-client";
export type { SessionBridge } from "./http-client";
