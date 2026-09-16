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
  global.fetch = mockFetch as unknown as typeof fetch;
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

  it("sends the photo bytes with the exact headers the presigned URL signed", async () => {
    // Expo's fetch overwrites Content-Type from blob.type for a Blob body. A
    // file:// response has no content type, so the header became "" and R2
    // rejected the signature. A typed array keeps the caller's headers.
    const bytes = new Uint8Array([255, 216, 255, 224, 0, 16]);
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        arrayBuffer: async () => bytes.buffer,
      } as unknown as Response)
      .mockResolvedValueOnce({ ok: true, status: 200 } as Response);
    mockPresign.mockResolvedValue({
      data: { url: "https://r2.example/put", key: "photos/1.jpg" },
    } as never);
    mockAnalyze.mockResolvedValue({ data: { id: 7, items: [] } } as never);

    await uploadAndAnalyze({ uri: "file:///meal.jpg", width: 1200, height: 900 }, "meal");

    expect(mockPresign).toHaveBeenCalledWith({
      content_type: "image/jpeg",
      content_length: bytes.byteLength,
    });
    const [url, init] = mockFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("https://r2.example/put");
    expect(init.method).toBe("PUT");
    expect(init.body).toBeInstanceOf(Uint8Array);
    expect(init.headers).toEqual({
      "Content-Type": "image/jpeg",
      "Content-Length": String(bytes.byteLength),
    });
  });
});
