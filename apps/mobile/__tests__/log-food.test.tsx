import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";

import LogFoodScreen from "../app/(app)/log-food";
import { useSession } from "../lib/session";

const mockCreateManualEntry = jest.fn<(...args: unknown[]) => Promise<{ status: number }>>();
const mockInvalidateQueries = jest.fn<() => Promise<void>>();

jest.mock("@macros/api-client", () => ({
  createManualEntry: (...args: unknown[]) => mockCreateManualEntry(...args),
  getGetDayQueryKey: (localDate: string) => ["day", localDate],
}));
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));
jest.mock("expo-router", () => ({
  router: { back: jest.fn(), replace: jest.fn() },
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
  mockCreateManualEntry.mockResolvedValue({ status: 201 });
  mockInvalidateQueries.mockResolvedValue(undefined);
});

describe("LogFoodScreen", () => {
  it("rejects a form without a name or positive macro", () => {
    render(<LogFoodScreen />);

    fireEvent.press(screen.getByRole("button", { name: "SAVE FOOD" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a name, a positive quantity, and at least one macro value.",
    );
    expect(mockCreateManualEntry).not.toHaveBeenCalled();
  });

  it("treats blank macros as zero and opens Today after a save", async () => {
    render(<LogFoodScreen />);
    fillRequiredFields();

    fireEvent.press(screen.getByRole("button", { name: "SAVE FOOD" }));

    await waitFor(() =>
      expect(mockCreateManualEntry).toHaveBeenCalledWith(
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
    mockCreateManualEntry.mockRejectedValue(new Error("network"));
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
    expect(mockCreateManualEntry).not.toHaveBeenCalled();
  });
});
