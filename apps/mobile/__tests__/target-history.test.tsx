import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { listTargets } from "@macros/api-client";
import { fireEvent, render, screen } from "@testing-library/react-native";

import TargetHistoryScreen from "../app/(app)/target-history";

jest.mock("expo-router", () => ({ useRouter: () => ({ back: jest.fn() }) }));
jest.mock("@macros/api-client", () => ({ listTargets: jest.fn() }));

const mockList = listTargets as jest.MockedFunction<typeof listTargets>;

beforeEach(() => {
  jest.clearAllMocks();
  mockList.mockResolvedValue({
    status: 200,
    headers: new Headers(),
    data: [
      {
        id: 2,
        calories: 2150,
        protein_g: 180,
        fiber_g: 33,
        source: "manual",
        rationale: "",
        effective_from: "2026-08-01",
      },
      {
        id: 1,
        calories: 2180,
        protein_g: 176,
        fiber_g: 32,
        source: "onboarding",
        rationale: "Built from your answers.",
        effective_from: "2026-08-01",
      },
    ],
  } as Awaited<ReturnType<typeof listTargets>>);
});

describe("target history", () => {
  it("shows every same-day version with its year, source, and stored rationale", async () => {
    render(<TargetHistoryScreen />);
    expect(await screen.findAllByText("EFFECTIVE AUG 1, 2026")).toHaveLength(2);
    expect(screen.queryByText(/AUG 1 →/)).toBeNull();
    expect(screen.getByText("MANUAL")).toBeTruthy();
    expect(screen.getByText("ONBOARDING")).toBeTruthy();
    expect(screen.getByText("Built from your answers.")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    mockList.mockResolvedValue({ status: 200, data: [], headers: new Headers() } as Awaited<
      ReturnType<typeof listTargets>
    >);
    render(<TargetHistoryScreen />);
    expect(await screen.findByText("No target versions yet.")).toBeTruthy();
  });

  it("retries after a failure", async () => {
    mockList.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      status: 200,
      data: [],
      headers: new Headers(),
    } as Awaited<ReturnType<typeof listTargets>>);
    render(<TargetHistoryScreen />);
    expect(await screen.findByText(/Nothing on this screen changed/)).toBeTruthy();
    fireEvent.press(screen.getByText("TRY AGAIN"));
    expect(await screen.findByText("No target versions yet.")).toBeTruthy();
    expect(mockList).toHaveBeenCalledTimes(2);
  });
});
