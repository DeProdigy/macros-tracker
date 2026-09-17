import { ApiError, getGetDayQueryKey, type FoodAnalysisResult } from "@macros/api-client";
import { useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Image, Linking, Pressable, StyleSheet, TextInput, View } from "react-native";

import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Body, Caption, ErrorText, Label, Numeral, Title } from "@/components/ui/text";

import { ItemEditor } from "@/components/item-editor";
import {
  analysisItemToEditable,
  emptyEditableItem,
  type EditableFoodItem,
  isValidEditableItem,
  itemTotals,
  itemWriteRequest,
} from "@/lib/entry-items";
import { macroValue } from "@/lib/format";
import { entryTimingForDate, localIsoDate, parseLocalIsoDate } from "@/lib/local-day";
import { colors, radius, space, tapTarget, type } from "@/lib/theme";
import { savePhotoAnalysis, type SelectedPhoto, uploadAndAnalyze } from "@/lib/photo-analysis";
import { markFoodLogged, useSession } from "@/lib/session";

const GENERIC_ANALYSIS_ERROR = "Could not analyze this photo. Retry or use Manual.";
const MANUAL_ENTRY_HINT = "Manual entry is still available.";
const QUOTA_ANALYSIS_ERROR = `You reached the rolling photo-analysis limit. ${MANUAL_ENTRY_HINT}`;

function analysisErrorFields(body: unknown): { code: string | null; detail: string | null } {
  if (!body || typeof body !== "object") return { code: null, detail: null };

  const fields = body as Record<string, unknown>;
  return {
    code: typeof fields.code === "string" ? fields.code : null,
    detail: typeof fields.detail === "string" && fields.detail.trim() ? fields.detail : null,
  };
}

// Keep this allowlist narrow. An unknown status or code must use the reviewed generic copy.
function isDisplayableAnalysisError(status: number, code: string | null): boolean {
  return (
    (status === 502 &&
      (code === "food_analysis_failed" || code === "food_analysis_invalid_output")) ||
    (status === 422 && code === "food_analysis_no_food_visible")
  );
}

function analysisErrorMessage(detail: string): string {
  const sentence = detail.endsWith(".") ? detail : `${detail}.`;
  return `${sentence} ${MANUAL_ENTRY_HINT}`;
}

export default function PhotoScreen() {
  const session = useSession();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const today = localIsoDate(new Date());
  const requestedDate = Array.isArray(params.date) ? params.date[0] : params.date;
  const localDate =
    requestedDate && parseLocalIsoDate(requestedDate) && requestedDate <= today
      ? requestedDate
      : today;
  const [photo, setPhoto] = useState<SelectedPhoto | null>(null);
  const [description, setDescription] = useState("");
  const [analysis, setAnalysis] = useState<FoodAnalysisResult | null>(null);
  const [items, setItems] = useState<EditableFoodItem[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  if (session.status !== "signedIn") return null;

  const choose = async (camera: boolean) => {
    setError(null);
    if (camera) {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        setPermissionDenied(true);
        return;
      }
      setPermissionDenied(false);
    }
    const result = camera
      ? await ImagePicker.launchCameraAsync({ mediaTypes: ["images"], quality: 1 })
      : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 1 });
    if (!result.canceled) {
      const asset = result.assets[0];
      setPhoto({ uri: asset.uri, width: asset.width, height: asset.height });
      setAnalysis(null);
      setItems([]);
      setPermissionDenied(false);
    }
  };

  const analyze = async () => {
    if (!photo) return;
    setWorking(true);
    setError(null);
    try {
      const result = await uploadAndAnalyze(photo, description);
      setAnalysis(result);
      setItems(result.items.map(analysisItemToEditable));
    } catch (caught) {
      if (caught instanceof ApiError) {
        const { code, detail } = analysisErrorFields(caught.body);
        console.error("Photo analysis request failed.", { status: caught.status, code });
        if (caught.status === 429) {
          setError(QUOTA_ANALYSIS_ERROR);
        } else if (isDisplayableAnalysisError(caught.status, code) && detail) {
          setError(analysisErrorMessage(detail));
        } else {
          setError(GENERIC_ANALYSIS_ERROR);
        }
      } else {
        setError(GENERIC_ANALYSIS_ERROR);
      }
    } finally {
      setWorking(false);
    }
  };

  const save = async () => {
    if (!analysis) return;
    if (!items.every(isValidEditableItem)) {
      setError("Each item needs a name, positive quantity, and at least one macro value.");
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const context = entryTimingForDate(session.timezoneStatus, session.user.timezone, localDate);
      const response = await savePhotoAnalysis(
        analysis.analysis_id,
        context,
        items.map(itemWriteRequest),
      );
      if (response.status !== 201) throw new Error("Save failed.");
      await queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(context.local_date) });
      markFoodLogged(session);
      router.replace({ pathname: "/today", params: { date: localDate } });
    } catch {
      setError("Could not save this photo entry. Try again.");
    } finally {
      setWorking(false);
    }
  };

  const updateItem = (index: number, value: EditableFoodItem) => {
    setItems((current) => current.map((item, itemIndex) => (itemIndex === index ? value : item)));
  };

  const removeItem = (index: number) => {
    if (items.length === 1) {
      setError("An entry needs at least one item.");
      return;
    }
    setError(null);
    setItems((current) => current.filter((_, itemIndex) => itemIndex !== index));
  };

  const totals = itemTotals(items);

  return (
    <Screen contentStyle={styles.content} keyboard scroll>
      <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.link}>
        <Caption color={colors.accent}>CANCEL</Caption>
      </Pressable>
      <Label color={colors.accent} style={styles.eyebrow}>
        PHOTO LOG
      </Label>
      <Title style={styles.title}>{analysis ? "Review estimate" : "Photograph your meal"}</Title>

      {!analysis ? (
        <>
          <View style={styles.actions}>
            <Action label="TAKE PHOTO" onPress={() => void choose(true)} />
            <Action label="CHOOSE LIBRARY" onPress={() => void choose(false)} />
          </View>
          {permissionDenied ? (
            <View style={styles.permission}>
              <Body color={colors.textSecondary}>
                Camera access is off. Choose Library or enable Camera in iOS Settings.
              </Body>
              <Pressable
                accessibilityRole="button"
                onPress={() => void Linking.openSettings()}
                style={styles.link}
              >
                <Caption color={colors.accent}>OPEN SETTINGS</Caption>
              </Pressable>
            </View>
          ) : null}
          {photo ? (
            <Image
              accessibilityLabel="Selected meal"
              source={{ uri: photo.uri }}
              style={styles.photo}
            />
          ) : null}
          <Label style={styles.label}>DESCRIPTION (OPTIONAL)</Label>
          <TextInput
            accessibilityLabel="Meal description"
            multiline
            onChangeText={setDescription}
            placeholder="Chicken thighs, rice, and broccoli"
            placeholderTextColor={colors.textDim}
            style={styles.input}
            value={description}
          />
          <Button
            busy={working}
            disabled={!photo || working}
            onPress={() => void analyze()}
            style={styles.primary}
            title="Analyze photo"
          />
        </>
      ) : (
        <>
          <View style={styles.totals}>
            <Metric label="CALORIES" value={macroValue(totals.calories)} />
            <Metric label="PROTEIN" value={`${macroValue(totals.protein_g)}g`} />
            <Metric label="FIBER" value={`${macroValue(totals.fiber_g)}g`} />
          </View>
          {items.map((item, index) => (
            <ItemEditor
              key={item.clientId}
              label={`Item ${index + 1}`}
              value={item}
              onChange={(value) => updateItem(index, value)}
              onRemove={() => removeItem(index)}
              removeDisabled={items.length === 1}
            />
          ))}
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              setItems((current) => [...current, emptyEditableItem(`new-${Date.now()}`)])
            }
            style={styles.add}
          >
            <Caption color={colors.accent}>ADD MISSED ITEM</Caption>
          </Pressable>
          <Button
            busy={working}
            disabled={working}
            onPress={() => void save()}
            style={styles.primary}
            title={localDate === today ? "Save to today" : "Save to this day"}
          />
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              setAnalysis(null);
              setItems([]);
            }}
            style={styles.link}
          >
            <Caption color={colors.accent}>CHOOSE ANOTHER PHOTO</Caption>
          </Pressable>
        </>
      )}
      {error ? (
        <View>
          <ErrorText style={styles.error}>{error}</ErrorText>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.replace({ pathname: "/log-food", params: { date: localDate } })}
            style={styles.link}
          >
            <Caption color={colors.accent}>USE MANUAL</Caption>
          </Pressable>
        </View>
      ) : null}
    </Screen>
  );
}

function Action({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.action}>
      <Caption color={colors.text}>{label}</Caption>
    </Pressable>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <View style={styles.metric}>
      <Numeral style={styles.metricValue}>{value}</Numeral>
      <Label style={styles.metricLabel}>{label}</Label>
    </View>
  );
}

const styles = StyleSheet.create({
  action: {
    alignItems: "center",
    backgroundColor: colors.surfaceRaised,
    borderRadius: radius.sm,
    flex: 1,
    justifyContent: "center",
    minHeight: 52,
  },
  actions: { flexDirection: "row", gap: space.md },
  add: {
    alignItems: "center",
    borderColor: colors.accent,
    borderRadius: radius.sm,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 50,
  },
  content: { paddingBottom: space.section, paddingHorizontal: space.xl, paddingTop: space.lg },
  error: { marginBottom: space.md, marginTop: space.lg },
  eyebrow: { marginTop: space.xxl },
  input: {
    ...type.body,
    borderColor: colors.border,
    borderRadius: radius.sm,
    borderWidth: 1,
    color: colors.text,
    minHeight: 90,
    padding: space.md,
    textAlignVertical: "top",
  },
  label: { marginBottom: space.sm, marginTop: space.xl },
  link: { alignItems: "center", justifyContent: "center", minHeight: tapTarget },
  metric: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    flex: 1,
    padding: space.md,
  },
  metricLabel: { marginTop: space.xs },
  metricValue: { fontSize: type.heading.fontSize },
  permission: { gap: space.md, marginTop: space.lg },
  photo: { borderRadius: radius.md, height: 260, marginTop: space.xl, width: "100%" },
  primary: { marginTop: space.xl },
  title: { marginBottom: space.xl, marginTop: space.sm },
  totals: { flexDirection: "row", gap: space.sm, marginBottom: space.xl },
});
