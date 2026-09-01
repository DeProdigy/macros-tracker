import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";

import PhotoScreen from "../app/(app)/photo";
import { savePhotoAnalysis, uploadAndAnalyze } from "../lib/photo-analysis";
import { useSession } from "../lib/session";

const mockInvalidateQueries = jest.fn<() => Promise<void>>();

jest.mock("@macros/api-client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(value: number) {
      super();
      this.status = value;
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
}));
jest.mock("../lib/local-day", () => ({
  localDayContext: () => ({ local_date: "2026-09-01", timezone: "UTC" }),
}));
jest.mock("../lib/photo-analysis", () => ({
  uploadAndAnalyze: jest.fn(),
  savePhotoAnalysis: jest.fn(),
}));
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
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
    user: { timezone: "UTC" },
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

describe("PhotoScreen", () => {
  it("keeps the selected photo and description after analysis failure", async () => {
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
    expect(screen.getByText("Chicken thigh")).toBeTruthy();
    expect(screen.getByText("Broccoli")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "SAVE TO TODAY" }));

    await waitFor(() => expect(mockSavePhotoAnalysis).toHaveBeenCalledWith(17, expect.any(Object)));
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["day", "2026-09-01"] });
    expect(router.replace).toHaveBeenCalledWith("/today");
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
