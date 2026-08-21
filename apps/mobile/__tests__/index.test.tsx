import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, useHealth } from "@macros/api-client";

import HomeScreen from "../app/index";
import { renderWithProviders } from "../test-utils/render";

// The generated hook is the seam. Mocking it lets each render branch be driven
// directly, with no network and no fake timers — what's under test here is the
// screen's handling of each state, not the transport (that's covered by the
// API's own tests).
jest.mock("@macros/api-client", () => {
  // A stand-in for the real ApiError, which the screen uses with `instanceof`.
  // Written with plain fields rather than TypeScript parameter properties:
  // babel rewrites those into assignments that jest's out-of-scope guard reads
  // as a reference to an external variable, and the suite fails to compile.
  class ApiError extends Error {
    status: number;
    body: unknown;

    constructor(status: number, body: unknown) {
      super(`API request failed with status ${status}`);
      this.status = status;
      this.body = body;
    }
  }

  return { useHealth: jest.fn(), ApiError };
});

type HealthResult = ReturnType<typeof useHealth>;

const mockUseHealth = useHealth as jest.MockedFunction<typeof useHealth>;

/**
 * `UseQueryResult` is a wide discriminated union — building a complete instance
 * would mean ~20 fields of noise per test. The screen reads exactly three, so
 * supply those and cast. Not `any`: the partial is still checked against the
 * real result type, so a renamed field fails to compile here too.
 */
const healthResult = (partial: Partial<HealthResult>): HealthResult => partial as HealthResult;

const okBody = {
  status: "ok",
  database: true,
  version: "0.1.0",
  timestamp: "2026-08-21T06:16:00Z",
};

describe("HomeScreen", () => {
  beforeEach(() => {
    mockUseHealth.mockReset();
  });

  it("shows a spinner while the check is in flight", () => {
    mockUseHealth.mockReturnValue(healthResult({ data: undefined, isPending: true }));

    const { getByText, queryByText } = renderWithProviders(<HomeScreen />);

    // Loading is the branch showing neither outcome: no status value yet, and
    // crucially not the error copy — a pending request must not read as a
    // failed one. Asserting both absences is what separates this branch from
    // the other two.
    expect(queryByText("ok")).toBeNull();
    expect(queryByText(/unreachable/i)).toBeNull();
    expect(getByText(/api health/i)).toBeTruthy();
  });

  it("renders the status, database, version and timestamp on success", () => {
    mockUseHealth.mockReturnValue(
      healthResult({
        data: { data: okBody } as HealthResult["data"],
        isPending: false,
      }),
    );

    const { getByText } = renderWithProviders(<HomeScreen />);

    expect(getByText("ok")).toBeTruthy();
    expect(getByText(/database reachable/i)).toBeTruthy();
    expect(getByText("v0.1.0")).toBeTruthy();
    expect(getByText("2026-08-21T06:16:00Z")).toBeTruthy();
  });

  it("renders the unhealthy body from a 503 instead of hiding it", () => {
    // The case worth having a screen for at all. The API answers 503 with a
    // full body naming the failed dependency, and React Query surfaces that as
    // a thrown error, so "unreachable" here would discard the only useful
    // detail: the process is up and the database is not.
    mockUseHealth.mockReturnValue(
      healthResult({
        data: undefined,
        isPending: false,
        error: new ApiError(503, { ...okBody, status: "unhealthy", database: false }),
      }),
    );

    const { getByText, queryByText } = renderWithProviders(<HomeScreen />);

    expect(getByText("unhealthy")).toBeTruthy();
    expect(getByText(/database unreachable/i)).toBeTruthy();
    expect(queryByText(/^unreachable$/)).toBeNull();
  });

  it("renders unreachable when the request fails with no usable body", () => {
    // A 502 from a proxy, a DNS failure, a timeout. Nothing to report but the
    // fact of it.
    mockUseHealth.mockReturnValue(
      healthResult({
        data: undefined,
        isPending: false,
        error: new ApiError(502, "<html>bad gateway</html>"),
      }),
    );

    const { getByText } = renderWithProviders(<HomeScreen />);

    expect(getByText(/unreachable/i)).toBeTruthy();
  });

  it("renders unreachable when the request succeeds with an empty body", () => {
    // isError is false but there's no payload — a 204 or a proxy returning an
    // empty 200. The screen must not fall through to reading `health.status`.
    mockUseHealth.mockReturnValue(healthResult({ data: undefined, isPending: false }));

    const { getByText } = renderWithProviders(<HomeScreen />);

    expect(getByText(/unreachable/i)).toBeTruthy();
  });
});
