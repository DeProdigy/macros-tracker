/**
 * Hand-written HTTP layer for the generated client.
 *
 * Orval calls `customFetch` for every generated operation. Everything that is
 * environment- or transport-specific lives here so the generated code in
 * src/generated/ stays a pure translation of the OpenAPI schema.
 *
 * This file is NOT generated. Do not move it into src/ — `clean` in
 * orval.config.ts wipes that directory on every run.
 *
 * MAC-31 made this the single choke point for auth: every request picks up the
 * access token here, and every 401 is answered here. Doing either per call is
 * how an app ends up with three different logout behaviours.
 */

/**
 * Base URL of the Django API.
 *
 * EXPO_PUBLIC_ vars are inlined into the app bundle at build time, so this must
 * never hold a secret. The fallback matches the local Django dev server.
 */
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

/** How long one attempt may take before this layer gives up on it. */
const DEFAULT_TIMEOUT_MS = 15_000;

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
 * Raised when an attempt runs past the timeout.
 *
 * A class of its own rather than an `ApiError` with an invented status: there
 * is no status, because no response arrived. Screens branch on
 * `ApiError.status`, and the first one to forget that 0 means "never happened"
 * shows the user a confident, wrong explanation.
 */
export class ApiTimeout extends Error {
  constructor(readonly timeoutMs: number) {
    super(`API request timed out after ${timeoutMs}ms`);
    this.name = "ApiTimeout";
  }
}

/**
 * Everything this layer needs from the app to keep a session alive.
 *
 * Injected rather than imported, because the token store is `expo-secure-store`
 * and the refresh call is a generated operation — both downstream of this
 * package. Importing the first would make @macros/api-client depend on Expo,
 * and importing the second would be a plain import cycle, since every generated
 * operation imports `customFetch` from this file.
 *
 * So: this package owns the *policy* (one refresh, one retry, never on a public
 * path), and apps/mobile owns the *bindings* (Keychain, which endpoint, where
 * to route afterwards).
 */
export type SessionBridge = {
  /** The stored access token, or null when signed out. */
  getAccessToken: () => Promise<string | null>;
  /**
   * Performs exactly one refresh and stores the result.
   *
   * Resolves with the new access token, or null when the session is
   * unrecoverable. Documented as never throwing, so the failure path stays a
   * value the queue below can hand to every waiter.
   */
  refresh: () => Promise<string | null>;
  /** Called once per expiry, after `refresh` gives up. Clears storage, routes to Welcome. */
  onSessionExpired: () => void;
  /**
   * Paths whose 401 must never trigger a refresh.
   *
   * Two live here and missing either is the same bug. Sign-in cannot be retried
   * with a token, so refreshing after a failed sign-in loops against an
   * endpoint that was never going to succeed. And refresh cannot refresh
   * itself.
   */
  publicPaths: readonly string[];
  /** Paths that opt out of the deadline. See `withTimeout` for why any do. */
  untimedPaths: readonly string[];
};

let bridge: SessionBridge | null = null;

/**
 * Installs, or with null removes, the session bridge.
 *
 * Called once at app start, before anything renders. With no bridge configured
 * `customFetch` behaves exactly as it did before MAC-31: no header, no retry.
 * That is what keeps the package usable from a script or a test with no
 * Keychain under it.
 */
export const configureSession = (next: SessionBridge | null): void => {
  bridge = next;
  refreshInFlight = null;
};

/**
 * The single in-flight refresh, shared by every caller waiting on one.
 *
 * **This variable is the whole point of MAC-31.** MAC-25 turns on
 * ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION, both correct. Now picture
 * three hooks mounting at once behind an expired access token. All three 401.
 * Fire three refreshes: the first rotates the token and blacklists the original,
 * then the other two present a blacklisted token, fail, and log the user out.
 * Correct auth code and correct security settings combining into a logout bug
 * that only shows up under concurrency, which is to say never in manual testing
 * of one screen and constantly on a real dashboard.
 *
 * One promise. Everyone awaits it. Cleared once it settles, so the *next*
 * expiry gets a refresh of its own.
 */
let refreshInFlight: Promise<string | null> | null = null;

const refreshOnce = (active: SessionBridge): Promise<string | null> => {
  if (refreshInFlight) {
    return refreshInFlight;
  }

  refreshInFlight = active
    .refresh()
    .then((accessToken) => {
      if (!accessToken) {
        // Fired inside the shared promise, so it happens once per expiry rather
        // than once per queued caller. Ten stranded requests must not produce
        // ten navigations to Welcome.
        active.onSessionExpired();
      }
      return accessToken;
    })
    .catch(() => {
      // The bridge is documented as never throwing, but a bug there must not
      // leave a rejected promise cached for every later caller to inherit.
      active.onSessionExpired();
      return null;
    })
    .finally(() => {
      refreshInFlight = null;
    });

  return refreshInFlight;
};

const pathOf = (url: string): string => url.split("?")[0] ?? url;

const matches = (url: string, paths: readonly string[]): boolean => paths.includes(pathOf(url));

/**
 * Runs one attempt under a deadline, without stamping on the caller's signal.
 *
 * React Query passes its cancellation signal into every generated operation, so
 * replacing `options.signal` outright would silently break query cancellation.
 * This builds a fresh controller and forwards an abort from either side.
 *
 * `AbortSignal.timeout` and `AbortSignal.any` each do this in one line and
 * neither is safe to assume on Hermes, so it is hand-rolled.
 */
const withTimeout = async (
  callerSignal: AbortSignal | null | undefined,
  send: (signal: AbortSignal) => Promise<Response>,
): Promise<Response> => {
  const controller = new AbortController();
  let timedOut = false;

  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, DEFAULT_TIMEOUT_MS);

  const forwardAbort = () => controller.abort();

  if (callerSignal?.aborted) {
    controller.abort();
  } else {
    callerSignal?.addEventListener("abort", forwardAbort);
  }

  try {
    return await send(controller.signal);
  } catch (error) {
    // Only our own timer becomes ApiTimeout. An abort the caller asked for
    // keeps its original shape, or React Query would report every cancelled
    // query as a timeout.
    if (timedOut) {
      throw new ApiTimeout(DEFAULT_TIMEOUT_MS);
    }
    throw error;
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", forwardAbort);
  }
};

/**
 * Flattens any `HeadersInit` into a plain object.
 *
 * `RequestInit.headers` is a union: a record, a `Headers` instance, or an array
 * of pairs. Spreading the last two yields `{}` and silently drops every header
 * the caller set, so normalize before merging. Duck-typed rather than
 * `instanceof Headers`, because the global is a polyfill in React Native and is
 * not guaranteed to be the same class the caller built from.
 */
const toHeaderRecord = (init: HeadersInit | undefined): Record<string, string> => {
  if (!init) {
    return {};
  }

  if (Array.isArray(init)) {
    return Object.fromEntries(init);
  }

  if (typeof (init as Headers).forEach === "function") {
    const record: Record<string, string> = {};
    (init as Headers).forEach((value, key) => {
      record[key] = value;
    });
    return record;
  }

  return { ...(init as Record<string, string>) };
};

/**
 * Orval's fetch client expects the mutator to resolve to the whole envelope
 * (`{ data, status, headers }`), not the bare body — the generated
 * `pingResponse` type is built that way. Returning just the body typechecks
 * against `T` but is wrong at runtime, so keep this shape in sync.
 */
export const customFetch = async <T>(url: string, options: RequestInit = {}): Promise<T> => {
  const active = bridge;
  const isPublic = !active || matches(url, active.publicPaths);
  const timed = !!active && !matches(url, active.untimedPaths);

  const send = async (accessToken: string | null): Promise<Response> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...toHeaderRecord(options.headers),
    };

    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }

    const fire = (signal?: AbortSignal): Promise<Response> =>
      fetch(`${API_BASE_URL}${url}`, { ...options, headers, signal: signal ?? options.signal });

    // A fresh deadline per attempt. Reusing one across the retry below would
    // hand attempt two a clock that has already run down.
    return timed ? withTimeout(options.signal, fire) : fire();
  };

  let response = await send(isPublic ? null : await active.getAccessToken());

  if (response.status === 401 && active && !isPublic) {
    const accessToken = await refreshOnce(active);

    // Exactly one retry. Looping here would hammer the API with a credential
    // the server has already refused.
    if (accessToken) {
      response = await send(accessToken);
    }
  }

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
