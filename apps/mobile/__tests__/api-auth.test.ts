/**
 * The mobile side of the refresh policy.
 *
 * `packages/api-client` decides *when* to refresh; this file decides what a
 * failed refresh means for the Keychain. The distinction under test: a server
 * that rejects the token is final, a server that could not be reached is not.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { configureSession, refreshSession, type SessionBridge } from "@macros/api-client";

import { clearTokens, getRefreshToken, saveTokens } from "../lib/auth-storage";
import { installApiAuth } from "../lib/api-auth";

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
    configureSession: jest.fn(),
    refreshSession: jest.fn(),
    getCreateSessionUrl: () => "/api/auth/sessions/",
    getRefreshSessionUrl: () => "/api/auth/sessions/refresh/",
  };
});

jest.mock("../lib/auth-storage", () => ({
  getAccessToken: jest.fn(),
  getRefreshToken: jest.fn(),
  saveTokens: jest.fn(),
  clearTokens: jest.fn(),
}));

const { ApiError } = jest.requireMock("@macros/api-client") as {
  ApiError: new (status: number, body: unknown) => Error & { status: number };
};

const mockConfigureSession = configureSession as jest.MockedFunction<typeof configureSession>;
const mockRefreshSession = refreshSession as jest.MockedFunction<typeof refreshSession>;
const mockGetRefreshToken = getRefreshToken as jest.MockedFunction<typeof getRefreshToken>;
const mockSaveTokens = saveTokens as jest.MockedFunction<typeof saveTokens>;
const mockClearTokens = clearTokens as jest.MockedFunction<typeof clearTokens>;

/** Installs the bridge and hands back the refresh function it registered. */
const bridgeRefresh = (): SessionBridge["refresh"] => {
  installApiAuth();
  const bridge = mockConfigureSession.mock.calls.at(-1)?.[0];
  if (!bridge) {
    throw new Error("installApiAuth did not configure a session bridge.");
  }
  return bridge.refresh;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockGetRefreshToken.mockResolvedValue("stored-refresh");
});

describe("refreshing the session", () => {
  it("stores the rotated pair and answers with the new access token", async () => {
    mockRefreshSession.mockResolvedValue({
      status: 200,
      data: { access: "new-access", refresh: "new-refresh" },
    } as Awaited<ReturnType<typeof refreshSession>>);

    await expect(bridgeRefresh()()).resolves.toEqual({
      status: "refreshed",
      accessToken: "new-access",
    });

    // Both halves, not just the access token: MAC-25 blacklists the refresh
    // token it was given, so keeping the old one would fail the next expiry.
    expect(mockSaveTokens).toHaveBeenCalledWith({
      access: "new-access",
      refresh: "new-refresh",
    });
  });

  it("reports expiry without a stored refresh token", async () => {
    mockGetRefreshToken.mockResolvedValue(null);

    await expect(bridgeRefresh()()).resolves.toEqual({ status: "expired" });
    expect(mockRefreshSession).not.toHaveBeenCalled();
  });

  it("reports unavailable when the Keychain read itself fails", async () => {
    // A locked Keychain is not an expired session. This used to throw straight
    // through the bridge and sign the user out.
    mockGetRefreshToken.mockRejectedValue(new Error("keychain locked"));

    await expect(bridgeRefresh()()).resolves.toEqual({ status: "unavailable" });
    expect(mockClearTokens).not.toHaveBeenCalled();
  });

  it.each([400, 401])("clears the tokens when the server rejects them (%i)", async (status) => {
    mockRefreshSession.mockRejectedValue(new ApiError(status, null));

    await expect(bridgeRefresh()()).resolves.toEqual({ status: "expired" });
    expect(mockClearTokens).toHaveBeenCalled();
  });

  it.each([500, 502])("keeps the tokens when the server is merely broken (%i)", async (status) => {
    mockRefreshSession.mockRejectedValue(new ApiError(status, null));

    // A 500 says nothing about the token. Reporting expiry here is the
    // self-inflicted logout MAC-31 exists to prevent, because upstream tears
    // the session down on that word. The next 401 gets another attempt.
    await expect(bridgeRefresh()()).resolves.toEqual({ status: "unavailable" });
    expect(mockClearTokens).not.toHaveBeenCalled();
  });

  it("keeps the tokens when the request never lands", async () => {
    mockRefreshSession.mockRejectedValue(new TypeError("Network request failed"));

    await expect(bridgeRefresh()()).resolves.toEqual({ status: "unavailable" });
    expect(mockClearTokens).not.toHaveBeenCalled();
  });
});
