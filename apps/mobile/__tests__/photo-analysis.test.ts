import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { createFoodAnalysis, presignUpload } from "@macros/api-client";
import { manipulateAsync } from "expo-image-manipulator";

import { uploadAndAnalyze } from "../lib/photo-analysis";

jest.mock("@macros/api-client", () => ({
  createEntry: jest.fn(),
  createFoodAnalysis: jest.fn(),
  presignUpload: jest.fn(),
}));
jest.mock("expo-image-manipulator", () => ({
  manipulateAsync: jest.fn(),
  SaveFormat: { JPEG: "jpeg" },
}));

const mockManipulate = manipulateAsync as jest.MockedFunction<typeof manipulateAsync>;
const mockPresign = presignUpload as jest.MockedFunction<typeof presignUpload>;
const mockAnalyze = createFoodAnalysis as jest.MockedFunction<typeof createFoodAnalysis>;
const mockFetch = jest.fn<typeof fetch>();

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = mockFetch;
  mockManipulate.mockResolvedValue({ uri: "file:///compressed.jpg" } as never);
});

describe("uploadAndAnalyze", () => {
  it("stops before presigning when the compressed image cannot be read", async () => {
    mockFetch.mockResolvedValue({ ok: false } as Response);

    await expect(
      uploadAndAnalyze({ uri: "file:///meal.jpg", width: 1200, height: 900 }, "meal"),
    ).rejects.toThrow("Could not read compressed photo.");

    expect(mockPresign).not.toHaveBeenCalled();
    expect(mockAnalyze).not.toHaveBeenCalled();
  });
});
