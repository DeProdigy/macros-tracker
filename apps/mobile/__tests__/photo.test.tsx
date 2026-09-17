import { ApiError } from "@macros/api-client";
import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";

import PhotoScreen from "../app/(app)/photo";
import { savePhotoAnalysis, uploadAndAnalyze } from "../lib/photo-analysis";
import { markFoodLogged, useSession } from "../lib/session";

const mockInvalidateQueries = jest.fn<() => Promise<void>>();

jest.mock("@macros/api-client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    body: unknown;
    constructor(value: number, body: unknown) {
      super();
      this.status = value;
      this.body = body;
    }
  },
  getGetDayQueryKey: (date: string) => ["day", date],
}));
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));
jest.mock("expo-image-picker", () => ({
  requestCameraPermissionsAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
  launchImageLibraryAsync: jest.fn(),
}));
jest.mock("expo-router", () => ({
  router: { back: jest.fn(), replace: jest.fn() },
  useLocalSearchParams: () => ({ date: "2026-09-01" }),
}));
jest.mock("../lib/local-day", () => ({
  entryTimingForDate: () => ({
    eaten_at: "2026-09-01T16:30:00Z",
    local_date: "2026-09-01",
    timezone: "UTC",
  }),
  localIsoDate: () => "2026-09-15",
  parseLocalIsoDate: () => new Date(2026, 8, 1),
}));
jest.mock("../lib/photo-analysis", () => ({
  uploadAndAnalyze: jest.fn(),
  savePhotoAnalysis: jest.fn(),
}));
jest.mock("../lib/session", () => ({
  useSession: jest.fn(),
  markFoodLogged: jest.fn(),
}));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockMarkFoodLogged = markFoodLogged as jest.MockedFunction<typeof markFoodLogged>;
const mockUploadAndAnalyze = uploadAndAnalyze as jest.MockedFunction<typeof uploadAndAnalyze>;
const mockSavePhotoAnalysis = savePhotoAnalysis as jest.MockedFunction<typeof savePhotoAnalysis>;
const mockLibrary = ImagePicker.launchImageLibraryAsync as jest.MockedFunction<
  typeof ImagePicker.launchImageLibraryAsync
>;
const mockCamera = ImagePicker.launchCameraAsync as jest.MockedFunction<
  typeof ImagePicker.launchCameraAsync
>;
const mockCameraPermission = ImagePicker.requestCameraPermissionsAsync as jest.MockedFunction<
  typeof ImagePicker.requestCameraPermissionsAsync
>;

const result = {
  analysis_id: 17,
  calories: "540.00",
  protein_g: "41.00",
  fiber_g: "8.00",
  items: [
    {
      name: "Chicken thigh",
      portion: "2 pieces",
      calories: "360.00",
      protein_g: "38.00",
      fiber_g: "0.00",
    },
    {
      name: "Broccoli",
      portion: "1 cup",
      calories: "180.00",
      protein_g: "3.00",
      fiber_g: "8.00",
    },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    timezoneStatus: "ready",
    user: { timezone: "UTC", has_logged_food: false },
  } as never);
  mockLibrary.mockResolvedValue({
    canceled: false,
    assets: [{ uri: "file:///meal.jpg", width: 1200, height: 900 }],
  } as never);
  mockCamera.mockResolvedValue({ canceled: true } as never);
  mockUploadAndAnalyze.mockResolvedValue(result);
  mockSavePhotoAnalysis.mockResolvedValue({ status: 201 } as never);
  mockInvalidateQueries.mockResolvedValue(undefined);
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("PhotoScreen", () => {
  it("shows an API detail and logs its code without the response body", async () => {
    const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
    mockUploadAndAnalyze.mockRejectedValue(
      new ApiError(502, {
        code: "food_analysis_invalid_output",
        detail: "Try another photo.",
      }),
    );
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Try another photo. Manual entry is still available.",
      ),
    );
    expect(consoleError).toHaveBeenCalledWith("Photo analysis request failed.", {
      status: 502,
      code: "food_analysis_invalid_output",
    });
  });

  it("keeps the quota message when the API returns a detail", async () => {
    const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
    mockUploadAndAnalyze.mockRejectedValue(
      new ApiError(429, {
        code: "food_analysis_quota_exceeded",
        detail: "API quota detail that the screen does not show.",
      }),
    );
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "You reached the rolling photo-analysis limit. Manual entry is still available.",
      ),
    );
    expect(screen.queryByText("API quota detail that the screen does not show.")).toBeNull();
    expect(consoleError).toHaveBeenCalledWith("Photo analysis request failed.", {
      status: 429,
      code: "food_analysis_quota_exceeded",
    });
  });

  it("uses the generic message for an unparsed API response", async () => {
    const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
    mockUploadAndAnalyze.mockRejectedValue(new ApiError(502, "<html>Bad gateway</html>"));
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Could not analyze this photo. Retry or use Manual.",
      ),
    );
    expect(consoleError).toHaveBeenCalledWith("Photo analysis request failed.", {
      status: 502,
      code: null,
    });
  });

  it("does not show a framework detail from an unrelated API response", async () => {
    const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
    mockUploadAndAnalyze.mockRejectedValue(
      new ApiError(401, {
        code: "token_not_valid",
        detail: "Given token not valid for any token type",
      }),
    );
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Could not analyze this photo. Retry or use Manual.",
      ),
    );
    expect(screen.queryByText("Given token not valid for any token type")).toBeNull();
    expect(consoleError).toHaveBeenCalledWith("Photo analysis request failed.", {
      status: 401,
      code: "token_not_valid",
    });
  });

  it("keeps the selected photo and description after a network failure", async () => {
    mockUploadAndAnalyze.mockRejectedValue(new Error("network"));
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.changeText(screen.getByLabelText("Meal description"), "two chicken thighs");
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/retry/i));
    expect(screen.getByLabelText("Selected meal")).toBeTruthy();
    expect(screen.getByDisplayValue("two chicken thighs")).toBeTruthy();
  });

  it("shows itemized totals and saves the analysis to Today", async () => {
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));

    await waitFor(() => expect(screen.getByText("540.00")).toBeTruthy());
    expect(screen.getByDisplayValue("Chicken thigh")).toBeTruthy();
    expect(screen.getByDisplayValue("Broccoli")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "SAVE TO THIS DAY" }));

    await waitFor(() =>
      expect(mockSavePhotoAnalysis).toHaveBeenCalledWith(17, expect.any(Object), [
        {
          name: "Chicken thigh",
          portion_label: "2 pieces",
          quantity: "1.00",
          calories: "360.00",
          protein_g: "38.00",
          fiber_g: "0.00",
        },
        {
          name: "Broccoli",
          portion_label: "1 cup",
          quantity: "1.00",
          calories: "180.00",
          protein_g: "3.00",
          fiber_g: "8.00",
        },
      ]),
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["day", "2026-09-01"] });
    // Records the first log in the cached user, so Today drops its first-run copy.
    expect(mockMarkFoodLogged).toHaveBeenCalled();
    expect(router.replace).toHaveBeenCalledWith({
      pathname: "/today",
      params: { date: "2026-09-01" },
    });
  });

  it("updates totals and the save payload after correction", async () => {
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));
    await waitFor(() => expect(screen.getByDisplayValue("Chicken thigh")).toBeTruthy());

    fireEvent.changeText(screen.getByLabelText("Item 1 quantity"), "2");
    expect(screen.getByText("900.00")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "SAVE TO THIS DAY" }));

    await waitFor(() =>
      expect(mockSavePhotoAnalysis).toHaveBeenCalledWith(
        17,
        expect.any(Object),
        expect.arrayContaining([
          expect.objectContaining({ name: "Chicken thigh", quantity: "2.00" }),
        ]),
      ),
    );
  });

  it("adds and removes items but keeps one item minimum", async () => {
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "CHOOSE LIBRARY" }));
    await waitFor(() => expect(screen.getByLabelText("Selected meal")).toBeTruthy());
    fireEvent.press(screen.getByRole("button", { name: "ANALYZE PHOTO" }));
    await waitFor(() => expect(screen.getAllByRole("button", { name: "REMOVE" })).toHaveLength(2));

    fireEvent.press(screen.getAllByRole("button", { name: "REMOVE" })[0]);
    expect(screen.queryByDisplayValue("Chicken thigh")).toBeNull();
    expect(screen.getByRole("button", { name: "REMOVE" })).toBeDisabled();

    fireEvent.press(screen.getByRole("button", { name: "ADD MISSED ITEM" }));
    expect(screen.getByLabelText("Item 2 food name")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "REMOVE" })).toHaveLength(2);
  });

  it("offers Library and Settings when camera permission is denied", async () => {
    mockCameraPermission.mockResolvedValue({ granted: false } as never);
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "TAKE PHOTO" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "OPEN SETTINGS" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "CHOOSE LIBRARY" })).toBeTruthy();
  });

  it("clears the denied banner as soon as camera permission is granted", async () => {
    mockCameraPermission
      .mockResolvedValueOnce({ granted: false } as never)
      .mockResolvedValueOnce({ granted: true } as never);
    render(<PhotoScreen />);
    fireEvent.press(screen.getByRole("button", { name: "TAKE PHOTO" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "OPEN SETTINGS" })).toBeTruthy());

    fireEvent.press(screen.getByRole("button", { name: "TAKE PHOTO" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "OPEN SETTINGS" })).toBeNull());
    expect(mockCamera).toHaveBeenCalledTimes(1);
  });
});
