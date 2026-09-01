import {
  createFoodAnalysis,
  createEntry,
  presignUpload,
  type FoodAnalysisResult,
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
  const blob = await imageResponse.blob();
  const upload = await presignUpload({ content_type: "image/jpeg", content_length: blob.size });
  // customFetch throws ApiError for every non-2xx generated response. Orval's
  // union does not encode that runtime invariant, so narrow only after the call.
  const uploadData = upload.data as PresignUploadResponse;
  const put = await fetch(uploadData.url, {
    method: "PUT",
    headers: { "Content-Type": "image/jpeg", "Content-Length": String(blob.size) },
    body: blob,
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
  context: { local_date: string; timezone: string },
) {
  return createEntry({
    ...context,
    eaten_at: new Date().toISOString(),
    analysis_id: analysisId,
  });
}
