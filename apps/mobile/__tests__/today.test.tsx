import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { render, screen } from "@testing-library/react-native";

import TodayScreen from "../app/(app)/today";
import { useSession } from "../lib/session";

const mockUseGetDay = jest.fn();
jest.mock("@macros/api-client", () => ({
  useGetDay: (...args: unknown[]) => mockUseGetDay(...args),
}));
jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    Link: ({ children }: { children: React.ReactNode }) => <Text>{children}</Text>,
    router: { push: jest.fn() },
  };
});
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    timezoneStatus: "ready",
    user: { timezone: "UTC" },
  } as never);
  mockUseGetDay.mockReturnValue({
    isLoading: false,
    data: {
      status: 200,
      data: {
        local_date: "2026-08-31",
        targets: null,
        calories: "0.00",
        protein_g: "0.00",
        fiber_g: "0.00",
        entries: [],
      },
    },
  });
});

describe("TodayScreen", () => {
  it("shows an empty day and a logging action", () => {
    render(<TodayScreen />);
    expect(screen.getByText("Nothing logged yet")).toBeTruthy();
    expect(screen.getByRole("button", { name: "LOG FOOD" })).toBeTruthy();
  });

  it("shows totals and entries returned by the day resource", () => {
    mockUseGetDay.mockReturnValue({
      isLoading: false,
      data: {
        status: 200,
        data: {
          local_date: "2026-08-31",
          targets: null,
          calories: "240.00",
          protein_g: "36.00",
          fiber_g: "4.00",
          entries: [
            {
              id: 1,
              description: "Greek yogurt",
              eaten_at: "2026-08-31T16:30:00Z",
              calories: "240.00",
              protein_g: "36.00",
              fiber_g: "4.00",
              source: "manual",
              items: [],
            },
          ],
        },
      },
    });
    render(<TodayScreen />);
    expect(screen.getByText("Greek yogurt")).toBeTruthy();
    expect(screen.getByText("240.00 kcal")).toBeTruthy();
    expect(screen.getByText("36.00p · 4.00f")).toBeTruthy();
  });
});
