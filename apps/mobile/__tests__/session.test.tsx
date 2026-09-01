/**
 * `SessionProvider` — restoring a session at launch, and ending one.
 *
 * The seams are the generated operations and the Keychain module, same pattern
 * as every other suite here. What is under test is which of the three states
 * the provider settles into, and what it tears down on the way out.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import {
  ApiError,
  deleteCurrentSession,
  deleteCurrentUser,
  getCurrentUser,
  updateCurrentUser,
  type User,
} from "@macros/api-client";
import { act, render, screen, waitFor } from "@testing-library/react-native";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppState, Text } from "react-native";

import { setSessionExpiredListener } from "../lib/api-auth";
import { clearTokens, getRefreshToken, getTokens } from "../lib/auth-storage";
import { deviceTimezone } from "../lib/local-day";
import { SessionProvider, useSession } from "../lib/session";

jest.mock("@macros/api-client", () => {
  class ApiError extends Error {
    status: number;
    body: unknown;

    constructor(status: number, body: unknown) {
      super(`API request failed with status ${status}`);
      this.status = status;
      this.body = body;
    }
  }

  return {
    ApiError,
    getCurrentUser: jest.fn(),
    updateCurrentUser: jest.fn(),
    deleteCurrentSession: jest.fn(),
    deleteCurrentUser: jest.fn(),
  };
});

jest.mock("../lib/auth-storage", () => ({
  getTokens: jest.fn(),
  getRefreshToken: jest.fn(),
  clearTokens: jest.fn(),
}));

jest.mock("../lib/local-day", () => ({ deviceTimezone: jest.fn() }));

// The bridge install is a module-load side effect that would reach into
// expo-secure-store. Captured here instead, so the expiry callback can be
// fired by hand.
jest.mock("../lib/api-auth", () => ({
  installApiAuth: jest.fn(),
  setSessionExpiredListener: jest.fn(),
}));

const mockGetCurrentUser = getCurrentUser as jest.MockedFunction<typeof getCurrentUser>;
const mockUpdateCurrentUser = updateCurrentUser as jest.MockedFunction<typeof updateCurrentUser>;
const mockDeleteCurrentSession = deleteCurrentSession as jest.MockedFunction<
  typeof deleteCurrentSession
>;
const mockDeleteCurrentUser = deleteCurrentUser as jest.MockedFunction<typeof deleteCurrentUser>;
const mockGetTokens = getTokens as jest.MockedFunction<typeof getTokens>;
const mockGetRefreshToken = getRefreshToken as jest.MockedFunction<typeof getRefreshToken>;
const mockClearTokens = clearTokens as jest.MockedFunction<typeof clearTokens>;
const mockDeviceTimezone = deviceTimezone as jest.MockedFunction<typeof deviceTimezone>;
const mockSetSessionExpiredListener = setSessionExpiredListener as jest.MockedFunction<
  typeof setSessionExpiredListener
>;

const user = { id: 1, name: "Alex", onboarding_completed: true, timezone: "UTC" } as User;

/**
 * Renders the session as text and hands back the live value.
 *
 * A ref rather than assertions on the strings alone, because `signOut` and
 * `deleteAccount` need calling from the test.
 */
const renderSession = () => {
  const captured: { current: ReturnType<typeof useSession> | null } = { current: null };

  const Probe = () => {
    const session = useSession();
    captured.current = session;
    return <Text>{session.status}</Text>;
  };

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const clearSpy = jest.spyOn(queryClient, "clear");

  render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <Probe />
      </SessionProvider>
    </QueryClientProvider>,
  );

  return { captured, clearSpy };
};

beforeEach(() => {
  jest.clearAllMocks();
  mockClearTokens.mockResolvedValue(undefined);
  mockGetRefreshToken.mockResolvedValue("stored-refresh");
  mockDeviceTimezone.mockReturnValue(null);
});

describe("restoring at launch", () => {
  it("settles on signedOut when the Keychain is empty", async () => {
    mockGetTokens.mockResolvedValue(null);

    renderSession();

    await waitFor(() => expect(screen.getByText("signedOut")).toBeTruthy());
    // No token means no question to ask the server.
    expect(mockGetCurrentUser).not.toHaveBeenCalled();
  });

  it("settles on signedIn with the user the server returned", async () => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockResolvedValue({
      status: 200,
      data: user,
    } as Awaited<ReturnType<typeof getCurrentUser>>);

    const { captured } = renderSession();

    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());
    expect(captured.current).toMatchObject({ status: "signedIn", user });
  });

  it("clears a token the server rejects", async () => {
    // A stored token is not a session. It may be expired, blacklisted, or
    // attached to an account that has since been deleted, and only the server
    // knows which.
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockRejectedValue(new ApiError(401, null));

    renderSession();

    await waitFor(() => expect(screen.getByText("signedOut")).toBeTruthy());
    expect(mockClearTokens).toHaveBeenCalled();
  });

  it("clears a token belonging to a deleted account", async () => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockRejectedValue(new ApiError(403, null));

    renderSession();

    await waitFor(() => expect(screen.getByText("signedOut")).toBeTruthy());
    expect(mockClearTokens).toHaveBeenCalled();
  });

  it.each([500, 502, 504])("keeps the tokens when the server is broken (%i)", async (status) => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockRejectedValue(new ApiError(status, null));

    renderSession();

    await waitFor(() => expect(screen.getByText("signedOut")).toBeTruthy());
    // Welcome is the right screen — there is no session to show yet. Wiping
    // the Keychain is not, because the next launch could have succeeded.
    expect(mockClearTokens).not.toHaveBeenCalled();
  });

  it("keeps the tokens when the device is offline", async () => {
    // The unrecoverable one. A cold start in airplane mode used to wipe the
    // Keychain, and no amount of reconnecting brought the session back.
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockRejectedValue(new TypeError("Network request failed"));

    renderSession();

    await waitFor(() => expect(screen.getByText("signedOut")).toBeTruthy());
    expect(mockClearTokens).not.toHaveBeenCalled();
  });
});

describe("timezone synchronization", () => {
  beforeEach(() => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockResolvedValue({ status: 200, data: user } as Awaited<
      ReturnType<typeof getCurrentUser>
    >);
  });

  it("patches a changed device timezone after session restore", async () => {
    mockDeviceTimezone.mockReturnValue("America/New_York");
    mockUpdateCurrentUser.mockResolvedValue({
      status: 200,
      data: { ...user, timezone: "America/New_York" },
    } as Awaited<ReturnType<typeof updateCurrentUser>>);

    const { captured } = renderSession();

    await waitFor(() => expect(captured.current?.timezoneStatus).toBe("ready"));
    expect(mockUpdateCurrentUser).toHaveBeenCalledWith({ timezone: "America/New_York" });
    expect(captured.current).toMatchObject({
      status: "signedIn",
      user: { timezone: "America/New_York" },
    });
  });

  it("patches a changed device timezone after a new sign-in", async () => {
    mockGetTokens.mockResolvedValue(null);
    mockDeviceTimezone.mockReturnValue("America/New_York");
    mockUpdateCurrentUser.mockResolvedValue({
      status: 200,
      data: { ...user, timezone: "America/New_York" },
    } as Awaited<ReturnType<typeof updateCurrentUser>>);
    const { captured } = renderSession();
    await waitFor(() => expect(captured.current?.status).toBe("signedOut"));

    await act(async () => {
      captured.current?.signIn(user);
    });

    await waitFor(() => expect(captured.current?.timezoneStatus).toBe("ready"));
    expect(mockUpdateCurrentUser).toHaveBeenCalledWith({ timezone: "America/New_York" });
  });

  it("does not patch when the stored timezone already matches", async () => {
    mockDeviceTimezone.mockReturnValue("UTC");

    const { captured } = renderSession();

    await waitFor(() => expect(captured.current?.timezoneStatus).toBe("ready"));
    expect(mockUpdateCurrentUser).not.toHaveBeenCalled();
  });

  it("keeps authentication and disables day work when synchronization fails", async () => {
    mockDeviceTimezone.mockReturnValue("Pacific/Auckland");
    mockUpdateCurrentUser.mockRejectedValue(new TypeError("Network request failed"));

    const { captured } = renderSession();

    await waitFor(() =>
      expect(mockUpdateCurrentUser).toHaveBeenCalledWith({ timezone: "Pacific/Auckland" }),
    );
    await waitFor(() => expect(captured.current?.timezoneStatus).toBe("unavailable"));
    expect(captured.current?.status).toBe("signedIn");
  });

  it("syncs a timezone change when the app returns to the foreground", async () => {
    let appStateListener: ((state: string) => void) | null = null;
    jest.spyOn(AppState, "addEventListener").mockImplementation((_event, listener) => {
      appStateListener = listener as (state: string) => void;
      return { remove: jest.fn() };
    });
    mockDeviceTimezone.mockReturnValue("UTC");
    mockUpdateCurrentUser.mockResolvedValue({
      status: 200,
      data: { ...user, timezone: "Pacific/Auckland" },
    } as Awaited<ReturnType<typeof updateCurrentUser>>);
    const { captured } = renderSession();
    await waitFor(() => expect(captured.current?.timezoneStatus).toBe("ready"));

    mockDeviceTimezone.mockReturnValue("Pacific/Auckland");
    await act(async () => {
      appStateListener?.("active");
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(mockUpdateCurrentUser).toHaveBeenCalledWith({ timezone: "Pacific/Auckland" }),
    );
    await waitFor(() =>
      expect(captured.current).toMatchObject({ user: { timezone: "Pacific/Auckland" } }),
    );
  });
});

describe("signing out", () => {
  beforeEach(() => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockResolvedValue({
      status: 200,
      data: user,
    } as Awaited<ReturnType<typeof getCurrentUser>>);
  });

  it("blacklists the refresh token, clears the Keychain and empties the cache", async () => {
    mockDeleteCurrentSession.mockResolvedValue({ status: 204 } as Awaited<
      ReturnType<typeof deleteCurrentSession>
    >);

    const { captured, clearSpy } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await captured.current?.signOut();
    });

    expect(mockDeleteCurrentSession).toHaveBeenCalledWith({ refresh: "stored-refresh" });
    expect(mockClearTokens).toHaveBeenCalled();
    // Or the next user on this device sees the previous one's cached data.
    expect(clearSpy).toHaveBeenCalled();
    expect(screen.getByText("signedOut")).toBeTruthy();
  });

  it("still signs out locally when the server call fails", async () => {
    // Sign-out that depends on a reachable server is sign-out that fails on a
    // train.
    mockDeleteCurrentSession.mockRejectedValue(new ApiError(401, null));

    const { captured } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await captured.current?.signOut();
    });

    // Once, not twice: the stored token is unchanged, so nothing rotated and a
    // second attempt would present the credential the server just refused.
    expect(mockDeleteCurrentSession).toHaveBeenCalledTimes(1);
    expect(mockClearTokens).toHaveBeenCalled();
    expect(screen.getByText("signedOut")).toBeTruthy();
  });

  it("blacklists the rotated token when the 401 handler refreshed mid-sign-out", async () => {
    // The scenario: the access token had expired, so the DELETE 401s,
    // customFetch refreshes — rotating the refresh token and blacklisting the
    // copy already captured in the request body — and the retry presents that
    // dead copy. Without the second attempt the token minted by that refresh
    // outlives the sign-out by up to REFRESH_TOKEN_LIFETIME.
    mockGetRefreshToken
      .mockResolvedValueOnce("stored-refresh")
      .mockResolvedValueOnce("rotated-refresh");
    mockDeleteCurrentSession
      .mockRejectedValueOnce(new ApiError(400, { refresh: "Token is invalid or expired." }))
      .mockResolvedValueOnce({ status: 204 } as Awaited<ReturnType<typeof deleteCurrentSession>>);

    const { captured } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await captured.current?.signOut();
    });

    expect(mockDeleteCurrentSession).toHaveBeenNthCalledWith(1, { refresh: "stored-refresh" });
    expect(mockDeleteCurrentSession).toHaveBeenNthCalledWith(2, { refresh: "rotated-refresh" });
    expect(mockClearTokens).toHaveBeenCalled();
    expect(screen.getByText("signedOut")).toBeTruthy();
  });

  it("gives up when the rotated token is refused too", async () => {
    // Two failures end it. The retry carries a freshly minted access token, so
    // a third round is not a state the 401 path can reach.
    mockGetRefreshToken
      .mockResolvedValueOnce("stored-refresh")
      .mockResolvedValueOnce("rotated-refresh");
    mockDeleteCurrentSession.mockRejectedValue(new ApiError(400, null));

    const { captured } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await captured.current?.signOut();
    });

    expect(mockDeleteCurrentSession).toHaveBeenCalledTimes(2);
    expect(mockClearTokens).toHaveBeenCalled();
    expect(screen.getByText("signedOut")).toBeTruthy();
  });
});

describe("deleting the account", () => {
  beforeEach(() => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockResolvedValue({
      status: 200,
      data: user,
    } as Awaited<ReturnType<typeof getCurrentUser>>);
  });

  it("clears the session after a successful delete", async () => {
    mockDeleteCurrentUser.mockResolvedValue({ status: 204 } as Awaited<
      ReturnType<typeof deleteCurrentUser>
    >);

    const { captured } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await captured.current?.deleteAccount();
    });

    expect(mockClearTokens).toHaveBeenCalled();
    expect(screen.getByText("signedOut")).toBeTruthy();
  });

  it("treats a 401 as already deleted", async () => {
    // Deleting twice is a no-op the API documents, and it answers 401 rather
    // than a second 204 because authentication rejects a deactivated account
    // before the view is reached.
    mockDeleteCurrentUser.mockRejectedValue(new ApiError(401, null));

    const { captured } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await captured.current?.deleteAccount();
    });

    expect(screen.getByText("signedOut")).toBeTruthy();
  });

  it("keeps the session when the delete fails for real", async () => {
    // Signing someone out of an account that still exists would tell them the
    // deletion worked.
    mockDeleteCurrentUser.mockRejectedValue(new ApiError(500, null));

    const { captured } = renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    await act(async () => {
      await expect(captured.current?.deleteAccount()).rejects.toBeInstanceOf(ApiError);
    });

    expect(mockClearTokens).not.toHaveBeenCalled();
    expect(screen.getByText("signedIn")).toBeTruthy();
  });
});

describe("the global 401 handler", () => {
  it("signs the app out when the bridge reports an unrecoverable session", async () => {
    mockGetTokens.mockResolvedValue({ access: "a", refresh: "r" });
    mockGetCurrentUser.mockResolvedValue({
      status: 200,
      data: user,
    } as Awaited<ReturnType<typeof getCurrentUser>>);

    renderSession();
    await waitFor(() => expect(screen.getByText("signedIn")).toBeTruthy());

    // The handler has no component to navigate from, so it moves this state
    // and the route guards follow.
    const expire = mockSetSessionExpiredListener.mock.calls[0]?.[0];
    expect(expire).toBeInstanceOf(Function);

    // Awaited, not synchronous: expiry runs the same teardown as sign-out, and
    // that clears the Keychain before it flips state.
    await act(async () => {
      expire?.();
    });

    expect(screen.getByText("signedOut")).toBeTruthy();
    // The whole point of routing expiry through endSession: a stale access
    // token left behind is one customFetch attaches to the next request.
    expect(mockClearTokens).toHaveBeenCalled();
  });
});
