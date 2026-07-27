/**
 * Hand-written HTTP layer for the generated client.
 *
 * Orval calls `customFetch` for every generated operation. Everything that is
 * environment- or transport-specific lives here so the generated code in
 * src/generated/ stays a pure translation of the OpenAPI schema.
 *
 * This file is NOT generated. Do not move it into src/ — `clean` in
 * orval.config.ts wipes that directory on every run.
 */

/**
 * Base URL of the Django API.
 *
 * EXPO_PUBLIC_ vars are inlined into the app bundle at build time, so this must
 * never hold a secret. The fallback matches the local Django dev server.
 */
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

/** Error carrying the HTTP status, so callers can branch on 401 vs 500. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    message?: string,
  ) {
    super(message ?? `API request failed with status ${status}`);
    this.name = "ApiError";
  }
}

/**
 * Orval's fetch client expects the mutator to resolve to the whole envelope
 * (`{ data, status, headers }`), not the bare body — the generated
 * `pingResponse` type is built that way. Returning just the body typechecks
 * against `T` but is wrong at runtime, so keep this shape in sync.
 */
export const customFetch = async <T>(url: string, options: RequestInit = {}): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  // 204 and other empty-body responses have nothing to parse.
  const raw = await response.text();
  let body: unknown;
  try {
    body = raw ? JSON.parse(raw) : undefined;
  } catch {
    // Not every failure comes back as JSON: Django's HTML debug page, a proxy
    // 502, a load balancer timeout. Parsing must not throw here or the status
    // below is lost and callers get an opaque SyntaxError instead of ApiError
    // — worst precisely when the failure is worst. Keep the raw text as the
    // body so the status stays actionable.
    body = raw;
  }

  if (!response.ok) {
    throw new ApiError(response.status, body);
  }

  return {
    data: body,
    status: response.status,
    headers: response.headers,
  } as T;
};
