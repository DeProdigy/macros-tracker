import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";

import LogFoodScreen from "../app/(app)/log-food";
import { useSession } from "../lib/session";

const mockCreateEntry = jest.fn<(...args: unknown[]) => Promise<{ status: number }>>();
const mockInvalidateQueries = jest.fn<() => Promise<void>>();
const mockRefetchFoods = jest.fn<() => Promise<void>>();
const mockFoodsQuery = {
  data: {
    status: 200,
    data: [
      {
        id: 42,
        name: "Greek yogurt",
        portion_label: "1 cup",
        calories: "120.00",
        protein_g: "18.00",
        fiber_g: "2.00",
      },
      {
        id: 43,
        name: "Avocado",
        portion_label: "half",
        calories: "160.00",
        protein_g: "2.00",
        fiber_g: "7.00",
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: mockRefetchFoods,
};
const mockUseGetFoods = jest.fn<(...args: unknown[]) => typeof mockFoodsQuery>(
  () => mockFoodsQuery,
);

jest.mock("@macros/api-client", () => ({
  createEntry: (...args: unknown[]) => mockCreateEntry(...args),
  getGetDayQueryKey: (localDate: string) => ["day", localDate],
  getGetFoodsQueryKey: () => ["foods"],
  useGetFoods: (...args: unknown[]) => mockUseGetFoods(...args),
}));
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));
jest.mock("expo-router", () => ({
  router: { back: jest.fn(), push: jest.fn(), replace: jest.fn() },
}));
jest.mock("../lib/local-day", () => {
  class LocalDayUnavailable extends Error {}
  return {
    LocalDayUnavailable,
    localDayContext: jest.fn(() => ({ local_date: "2026-08-31", timezone: "UTC" })),
  };
});
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

function fillRequiredFields() {
  fireEvent.changeText(screen.getByLabelText("Food name"), "Greek yogurt");
  fireEvent.changeText(screen.getByLabelText("CALORIES"), "120");
}

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    timezoneStatus: "ready",
    user: { timezone: "UTC" },
  } as never);
  mockCreateEntry.mockResolvedValue({ status: 201 });
  mockInvalidateQueries.mockResolvedValue(undefined);
  mockRefetchFoods.mockResolvedValue(undefined);
  mockFoodsQuery.data = {
    status: 200,
    data: [
      {
        id: 42,
        name: "Greek yogurt",
        portion_label: "1 cup",
        calories: "120.00",
        protein_g: "18.00",
        fiber_g: "2.00",
      },
      {
        id: 43,
        name: "Avocado",
        portion_label: "half",
        calories: "160.00",
        protein_g: "2.00",
        fiber_g: "7.00",
      },
    ],
  };
  mockFoodsQuery.isLoading = false;
  mockFoodsQuery.isError = false;
});

describe("LogFoodScreen", () => {
  it("opens the Photo flow", () => {
    render(<LogFoodScreen />);

    fireEvent.press(screen.getByRole("button", { name: "PHOTO" }));

    expect(router.push).toHaveBeenCalledWith("/photo");
  });

  it("rejects a form without a name or positive macro", () => {
    render(<LogFoodScreen />);

    fireEvent.press(screen.getByRole("button", { name: "SAVE FOOD" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a name, a positive quantity, and at least one macro value.",
    );
    expect(mockCreateEntry).not.toHaveBeenCalled();
  });

  it("treats blank macros as zero and opens Today after a save", async () => {
    render(<LogFoodScreen />);
    fillRequiredFields();

    fireEvent.press(screen.getByRole("button", { name: "SAVE FOOD" }));

    await waitFor(() =>
      expect(mockCreateEntry).toHaveBeenCalledWith(
        expect.objectContaining({
          item: expect.objectContaining({
            calories: "120",
            protein_g: "0",
            fiber_g: "0",
          }),
        }),
      ),
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: ["day", "2026-08-31"],
    });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/today"));
  });

  it("keeps the input when the save fails", async () => {
    mockCreateEntry.mockRejectedValue(new Error("network"));
    render(<LogFoodScreen />);
    fillRequiredFields();

    fireEvent.press(screen.getByRole("button", { name: "SAVE FOOD" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Could not save this food. Try again."),
    );
    expect(screen.getByDisplayValue("Greek yogurt")).toBeTruthy();
    expect(screen.getByDisplayValue("120")).toBeTruthy();
  });

  it("explains when the local day is unavailable", async () => {
    const { LocalDayUnavailable, localDayContext } = jest.requireMock("../lib/local-day") as {
      LocalDayUnavailable: new () => Error;
      localDayContext: jest.Mock;
    };
    localDayContext.mockImplementationOnce(() => {
      throw new LocalDayUnavailable();
    });
    render(<LogFoodScreen />);
    fillRequiredFields();

    fireEvent.press(screen.getByRole("button", { name: "SAVE FOOD" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Sync your timezone and try again."),
    );
    expect(mockCreateEntry).not.toHaveBeenCalled();
  });

  it("loads Recents and sends case-insensitive search to the API", () => {
    render(<LogFoodScreen />);

    fireEvent.press(screen.getByRole("button", { name: "RECENTS" }));
    fireEvent.changeText(screen.getByLabelText("Search recent foods"), " YOGURT ");

    expect(mockUseGetFoods).toHaveBeenLastCalledWith(
      { search: "YOGURT" },
      expect.objectContaining({ query: { enabled: true } }),
    );
    expect(screen.getByText("Greek yogurt")).toBeTruthy();
  });

  it("previews quantity-adjusted macros and creates a new Recent entry", async () => {
    render(<LogFoodScreen />);
    fireEvent.press(screen.getByRole("button", { name: "RECENTS" }));
    fireEvent.press(screen.getByRole("button", { name: "Select Greek yogurt" }));

    expect(screen.getByLabelText("Macro preview")).toHaveTextContent(
      "120.00 kcal · 18.00p · 2.00f",
    );
    fireEvent.changeText(screen.getByLabelText("Recent quantity"), "1.5");
    expect(screen.getByLabelText("Macro preview")).toHaveTextContent(
      "180.00 kcal · 27.00p · 3.00f",
    );
    fireEvent.press(screen.getByRole("button", { name: "LOG AGAIN" }));

    await waitFor(() =>
      expect(mockCreateEntry).toHaveBeenCalledWith(
        expect.objectContaining({ recent_item_id: 42, quantity: "1.50" }),
      ),
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith({
      queryKey: ["day", "2026-08-31"],
    });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["foods"] });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/today"));
  });

  it("keeps the selected Recent and quantity when saving fails", async () => {
    mockCreateEntry.mockRejectedValue(new Error("network"));
    render(<LogFoodScreen />);
    fireEvent.press(screen.getByRole("button", { name: "RECENTS" }));
    fireEvent.press(screen.getByRole("button", { name: "Select Greek yogurt" }));
    fireEvent.changeText(screen.getByLabelText("Recent quantity"), "2.25");

    fireEvent.press(screen.getByRole("button", { name: "LOG AGAIN" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Could not log this recent food. Try again.",
      ),
    );
    expect(screen.getByDisplayValue("2.25")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Collapse Greek yogurt" })).toBeTruthy();
  });

  it("shows the empty Recents state", () => {
    mockFoodsQuery.data = { status: 200, data: [] };
    render(<LogFoodScreen />);

    fireEvent.press(screen.getByRole("button", { name: "RECENTS" }));

    expect(screen.getByText("No recent foods found")).toBeTruthy();
    expect(screen.getByText("Log a food manually and it will appear here.")).toBeTruthy();
  });

  it("shows a retry action when Recents fail to load", () => {
    mockFoodsQuery.isError = true;
    render(<LogFoodScreen />);
    fireEvent.press(screen.getByRole("button", { name: "RECENTS" }));

    fireEvent.press(screen.getByRole("button", { name: "TRY AGAIN" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your recent foods.");
    expect(mockRefetchFoods).toHaveBeenCalledTimes(1);
  });
});
