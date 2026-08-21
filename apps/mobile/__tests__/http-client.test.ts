/**
 * The global 401 handler, tested against the real `customFetch`.
 *
 * Not a mock of the package: `fetch` is the seam instead, so what is under test
 * is the actual code every generated hook runs through. The concurrency case
 * below is the reason MAC-31 exists, and mocking the layer that implements it
 * would have tested nothing.
 *
 * The file lives in apps/mobile rather than in packages/api-client because the
 * app is the package's only consumer and already owns a jest setup. Jest
 * resolves the workspace symlink to the real path, so `@macros/api-client` here
 * is the source, transformed like any other file in the repo.
 */

import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, ApiTimeout, configureSession, customFetch } from "@macros/api-client";

const SIGN_IN = "/api/auth/sessions/";
const REFRESH = "/api/auth/sessions/refresh/";
const ME = "/api/users/me/";

const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** A promise plus its resolver, for holding a request open mid-flight. */
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
};

const mockFetch = jest.fn<typeof fetch>();
const getAccessToken = jest.fn<() => Promise<string | null>>();
const refresh = jest.fn<() => Promise<string | null>>();
const onSessionExpired = jest.fn<() => void>();

const authHeaderOf = (call: number): string | null => {
  const init = mockFetch.mock.calls[call]?.[1];
  const headers = init?.headers as Record<string, string> | undefined;
  return headers?.Authorization ?? null;
};

beforeEach(() => {
  mockFetch.mockReset();
  getAccessToken.mockReset();
  refresh.mockReset();
  onSessionExpired.mockReset();

  global.fetch = mockFetch as unknown as typeof fetch;

  getAccessToken.mockResolvedValue("stale-access");
  refresh.mockResolvedValue("fresh-access");

  configureSession({
    getAccessToken,
    refresh,
    onSessionExpired,
    publicPaths: [SIGN_IN, REFRESH],
    untimedPaths: [REFRESH],
  });
});

afterEach(() => {
  // Leaving a bridge installed would leak the mocks into every other suite that
  // touches the client.
  configureSession(null);
});

describe("attaching the access token", () => {
  it("sends the stored token as a bearer header", async () => {
    mockFetch.mockResolvedValue(jsonResponse(200, { id: 1 }));

    await customFetch(ME, { method: "GET" });

    expect(authHeaderOf(0)).toBe("Bearer stale-access");
  });

  it("sends no header when there is no token", async () => {
    getAccessToken.mockResolvedValue(null);
    mockFetch.mockResolvedValue(jsonResponse(200, {}));

    await customFetch(ME, { method: "GET" });

    expect(authHeaderOf(0)).toBeNull();
  });

  it("sends no header to a public path, even while signed in", async () => {
    mockFetch.mockResolvedValue(jsonResponse(201, {}));

    await customFetch(SIGN_IN, { method: "POST" });

    expect(authHeaderOf(0)).toBeNull();
    expect(getAccessToken).not.toHaveBeenCalled();
  });
});

describe("the 401 path", () => {
  it("refreshes once, then retries the original request with the new token", async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(jsonResponse(200, { id: 7 }));

    const result = await customFetch<{ data: { id: number }; status: number }>(ME, {
      method: "GET",
    });

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(authHeaderOf(1)).toBe("Bearer fresh-access");
    expect(result.data).toEqual({ id: 7 });
  });

  it("retries exactly once — a second 401 surfaces rather than looping", async () => {
    mockFetch.mockResolvedValue(jsonResponse(401, { detail: "still no" }));

    await expect(customFetch(ME, { method: "GET" })).rejects.toBeInstanceOf(ApiError);

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh when the sign-in endpoint itself answers 401", async () => {
    mockFetch.mockResolvedValue(jsonResponse(401, {}));

    await expect(customFetch(SIGN_IN, { method: "POST" })).rejects.toBeInstanceOf(ApiError);

    expect(refresh).not.toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("does not refresh on a status that is not 401", async () => {
    mockFetch.mockResolvedValue(jsonResponse(500, {}));

    await expect(customFetch(ME, { method: "GET" })).rejects.toBeInstanceOf(ApiError);

    expect(refresh).not.toHaveBeenCalled();
  });
});

/**
 * The bug this ticket was written to prevent.
 *
 * MAC-25 rotates refresh tokens and blacklists the old one. Three concurrent
 * refreshes therefore mean two requests presenting a blacklisted token, two
 * failures, and a logout — from correct auth code and correct security
 * settings. It only appears under concurrency, so only a test like this catches
 * it.
 */
describe("concurrent 401s", () => {
  it("produces exactly one refresh, with every caller awaiting the same promise", async () => {
    const gate = deferred<string | null>();
    refresh.mockReturnValue(gate.promise);

    mockFetch.mockImplementation(async (_input, init) => {
      const headers = init?.headers as Record<string, string> | undefined;
      return headers?.Authorization === "Bearer fresh-access"
        ? jsonResponse(200, { ok: true })
        : jsonResponse(401, { detail: "expired" });
    });

    const inFlight = Promise.all([
      customFetch(ME, { method: "GET" }),
      customFetch("/api/uploads/", { method: "POST" }),
      customFetch("/api/analyses/", { method: "POST" }),
    ]);

    // Let all three reach their 401 and queue behind the refresh before it
    // resolves. Resolving first would let them run one after another and the
    // test would pass without proving anything.
    await Promise.resolve();
    await Promise.resolve();

    gate.resolve("fresh-access");
    await inFlight;

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(onSessionExpired).not.toHaveBeenCalled();
    // Three first attempts, three retries.
    expect(mockFetch).toHaveBeenCalledTimes(6);
  });

  it("expires the session once, not once per stranded request", async () => {
    const gate = deferred<string | null>();
    refresh.mockReturnValue(gate.promise);
    mockFetch.mockResolvedValue(jsonResponse(401, { detail: "expired" }));

    const inFlight = Promise.allSettled([
      customFetch(ME, { method: "GET" }),
      customFetch("/api/uploads/", { method: "POST" }),
      customFetch("/api/analyses/", { method: "POST" }),
    ]);

    await Promise.resolve();
    await Promise.resolve();

    gate.resolve(null);
    const results = await inFlight;

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
    // Each caller still gets its own original failure.
    expect(results.every((result) => result.status === "rejected")).toBe(true);
  });

  it("lets a later expiry start a fresh refresh", async () => {
    mockFetch
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, {}))
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, {}));

    await customFetch(ME, { method: "GET" });
    await customFetch(ME, { method: "GET" });

    // The shared promise is cleared when it settles, or the second expiry would
    // reuse an access token the server has already aged out.
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});

describe("a refresh that gives up", () => {
  it("expires the session and rethrows the original 401", async () => {
    refresh.mockResolvedValue(null);
    mockFetch.mockResolvedValue(jsonResponse(401, { detail: "gone" }));

    await expect(customFetch(ME, { method: "GET" })).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
    });

    expect(onSessionExpired).toHaveBeenCalledTimes(1);
    // No retry: there was no token to retry with.
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("treats a throwing bridge as a give-up rather than caching a rejection", async () => {
    refresh.mockRejectedValue(new Error("keychain unavailable"));
    mockFetch.mockResolvedValue(jsonResponse(401, {}));

    await expect(customFetch(ME, { method: "GET" })).rejects.toBeInstanceOf(ApiError);
    expect(onSessionExpired).toHaveBeenCalledTimes(1);

    // The next call must get a clean attempt, not the stored rejection.
    refresh.mockResolvedValue("fresh-access");
    mockFetch.mockReset();
    mockFetch
      .mockResolvedValueOnce(jsonResponse(401, {}))
      .mockResolvedValueOnce(jsonResponse(200, {}));

    await expect(customFetch(ME, { method: "GET" })).resolves.toBeDefined();
  });
});

describe("with no bridge configured", () => {
  it("behaves as it did before MAC-31", async () => {
    configureSession(null);
    mockFetch.mockResolvedValue(jsonResponse(401, {}));

    await expect(customFetch(ME, { method: "GET" })).rejects.toBeInstanceOf(ApiError);

    expect(authHeaderOf(0)).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

describe("the deadline", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("aborts an attempt that runs long and reports it as a timeout", async () => {
    mockFetch.mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new Error("Aborted")));
        }),
    );

    const request = customFetch(ME, { method: "GET" });
    const assertion = expect(request).rejects.toBeInstanceOf(ApiTimeout);

    await jest.advanceTimersByTimeAsync(15_000);
    await assertion;
  });

  it("leaves the refresh call alone", async () => {
    // Aborting a refresh does not cancel it. The server may already have
    // rotated the token and blacklisted the copy in the Keychain, so a
    // client-side deadline here causes the logout the rest of this file
    // prevents.
    mockFetch.mockImplementation(
      (_input, init) =>
        new Promise((resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new Error("Aborted")));
          setTimeout(() => resolve(jsonResponse(200, { access: "a", refresh: "r" })), 30_000);
        }),
    );

    const request = customFetch(REFRESH, { method: "POST" });

    await jest.advanceTimersByTimeAsync(30_000);
    await expect(request).resolves.toBeDefined();
  });
});
