import { describe, expect, it, jest, beforeEach } from "@jest/globals";
import { usePing } from "@macros/api-client";

import HomeScreen from "../app/index";
import { renderWithProviders } from "../test-utils/render";

// The generated hook is the seam. Mocking it lets each of the three render
// branches be driven directly, with no network and no fake timers — what's
// under test here is the screen's handling of each state, not the transport
// (that's covered by the API's own tests).
jest.mock("@macros/api-client", () => ({
  usePing: jest.fn(),
}));

type PingResult = ReturnType<typeof usePing>;

const mockUsePing = usePing as jest.MockedFunction<typeof usePing>;

/**
 * `UseQueryResult` is a wide discriminated union — building a complete instance
 * would mean ~20 fields of noise per test. The screen reads exactly three, so
 * supply those and cast. Not `any`: the partial is still checked against the
 * real result type, so a renamed field fails to compile here too.
 */
const pingResult = (partial: Partial<PingResult>): PingResult => partial as PingResult;

describe("HomeScreen", () => {
  beforeEach(() => {
    mockUsePing.mockReset();
  });

  it("shows a spinner while the ping is in flight", () => {
    mockUsePing.mockReturnValue(pingResult({ data: undefined, isPending: true, isError: false }));

    const { getByText, queryByText } = renderWithProviders(<HomeScreen />);

    // Loading is the branch showing neither outcome: no status value yet, and
    // crucially not the error copy — a pending request must not read as a
    // failed one. Asserting both absences is what separates this branch from
    // the other two.
    expect(queryByText("ok")).toBeNull();
    expect(queryByText(/unreachable/i)).toBeNull();
    expect(getByText(/api status/i)).toBeTruthy();
  });

  it("renders the status, version and timestamp on success", () => {
    mockUsePing.mockReturnValue(
      pingResult({
        data: {
          data: {
            status: "ok",
            version: "0.1.0",
            timestamp: "2026-07-23T12:34:56Z",
          },
        } as PingResult["data"],
        isPending: false,
        isError: false,
      }),
    );

    const { getByText } = renderWithProviders(<HomeScreen />);

    expect(getByText("ok")).toBeTruthy();
    expect(getByText("v0.1.0")).toBeTruthy();
    expect(getByText("2026-07-23T12:34:56Z")).toBeTruthy();
  });

  it("renders an unreachable message when the request fails", () => {
    mockUsePing.mockReturnValue(pingResult({ data: undefined, isPending: false, isError: true }));

    const { getByText } = renderWithProviders(<HomeScreen />);

    expect(getByText(/unreachable/i)).toBeTruthy();
  });

  it("renders unreachable when the request succeeds with an empty body", () => {
    // isError is false but there's no payload — a 204 or a proxy returning an
    // empty 200. The screen must not fall through to reading `ping.status`.
    mockUsePing.mockReturnValue(pingResult({ data: undefined, isPending: false, isError: false }));

    const { getByText } = renderWithProviders(<HomeScreen />);

    expect(getByText(/unreachable/i)).toBeTruthy();
  });
});
