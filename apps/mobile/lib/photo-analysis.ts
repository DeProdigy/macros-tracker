import {
  createFoodAnalysis,
  createEntry,
  presignUpload,
  type FoodAnalysisResult,
  type FoodItemWriteRequest,
  type PresignUploadResponse,
} from "@macros/api-client";
import { manipulateAsync, SaveFormat } from "expo-image-manipulator";

export type SelectedPhoto = { uri: string; width: number; height: number };

export async function uploadAndAnalyze(
  photo: SelectedPhoto,
  description: string,
): Promise<FoodAnalysisResult> {
  const resize =
    photo.width >= photo.height
      ? { width: Math.min(photo.width, 1600) }
      : { height: Math.min(photo.height, 1600) };
  const compressed = await manipulateAsync(photo.uri, [{ resize }], {
    compress: 0.78,
    format: SaveFormat.JPEG,
  });
  const imageResponse = await fetch(compressed.uri);
  if (!imageResponse.ok) throw new Error("Could not read compressed photo.");
  // Send bytes, never a Blob. The presigned URL signs Content-Type and
  // Content-Length, so R2 answers 403 SignatureDoesNotMatch if either header
  // changes in flight. Expo replaces the global fetch, and for a Blob body it
  // overwrites Content-Type with blob.type even when the caller set the header.
  // A file:// response carries no content type, so blob.type is "". A typed
  // array takes a different branch in Expo's fetch and keeps these headers.
  const bytes = new Uint8Array(await imageResponse.arrayBuffer());
  const upload = await presignUpload({
    content_type: "image/jpeg",
    content_length: bytes.byteLength,
  });
  // customFetch throws ApiError for every non-2xx generated response. Orval's
  // union does not encode that runtime invariant, so narrow only after the call.
  const uploadData = upload.data as PresignUploadResponse;
  const put = await fetch(uploadData.url, {
    method: "PUT",
    headers: { "Content-Type": "image/jpeg", "Content-Length": String(bytes.byteLength) },
    body: bytes,
  });
  if (!put.ok) throw new Error("Could not upload photo.");
  const analysis = await createFoodAnalysis({
    photo_key: uploadData.key,
    description: description.trim(),
  });
  return analysis.data as FoodAnalysisResult;
}

export async function savePhotoAnalysis(
  analysisId: number,
  timing: { eaten_at: string; local_date: string; timezone: string },
  items: FoodItemWriteRequest[],
) {
  return createEntry({
    ...timing,
    analysis_id: analysisId,
    items,
  });
}
