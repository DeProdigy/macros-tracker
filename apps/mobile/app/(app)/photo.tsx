import { ApiError, getGetDayQueryKey, type FoodAnalysisResult } from "@macros/api-client";
import { useQueryClient } from "@tanstack/react-query";
import * as ImagePicker from "expo-image-picker";
import { router } from "expo-router";
import { useState } from "react";
import {
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { localDayContext } from "@/lib/local-day";
import { usePalette } from "@/lib/palette";
import { savePhotoAnalysis, type SelectedPhoto, uploadAndAnalyze } from "@/lib/photo-analysis";
import { useSession } from "@/lib/session";

export default function PhotoScreen() {
  const palette = usePalette();
  const session = useSession();
  const queryClient = useQueryClient();
  const [photo, setPhoto] = useState<SelectedPhoto | null>(null);
  const [description, setDescription] = useState("");
  const [analysis, setAnalysis] = useState<FoodAnalysisResult | null>(null);
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
      setPermissionDenied(false);
    }
  };

  const analyze = async () => {
    if (!photo) return;
    setWorking(true);
    setError(null);
    try {
      setAnalysis(await uploadAndAnalyze(photo, description));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 429) {
        setError("You reached the rolling photo-analysis limit. Manual entry is still available.");
      } else {
        setError("Could not analyze this photo. Retry or use Manual.");
      }
    } finally {
      setWorking(false);
    }
  };

  const save = async () => {
    if (!analysis) return;
    setWorking(true);
    setError(null);
    try {
      const context = localDayContext(session.timezoneStatus, session.user.timezone);
      const response = await savePhotoAnalysis(analysis.analysis_id, context);
      if (response.status !== 201) throw new Error("Save failed.");
      await queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(context.local_date) });
      router.replace("/today");
    } catch {
      setError("Could not save this photo entry. Try again.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <ScrollView
      style={{ backgroundColor: palette.background }}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Pressable accessibilityRole="button" onPress={() => router.back()}>
        <Text style={{ color: palette.accent }}>CANCEL</Text>
      </Pressable>
      <Text style={[styles.eyebrow, { color: palette.accent }]}>PHOTO LOG</Text>
      <Text style={[styles.title, { color: palette.text }]}>
        {analysis ? "Review estimate" : "Photograph your meal"}
      </Text>

      {!analysis ? (
        <>
          <View style={styles.actions}>
            <Action label="TAKE PHOTO" onPress={() => void choose(true)} />
            <Action label="CHOOSE LIBRARY" onPress={() => void choose(false)} />
          </View>
          {permissionDenied ? (
            <View style={styles.permission}>
              <Text style={{ color: palette.secondaryText }}>
                Camera access is off. Choose Library or enable Camera in iOS Settings.
              </Text>
              <Pressable accessibilityRole="button" onPress={() => void Linking.openSettings()}>
                <Text style={{ color: palette.accent }}>OPEN SETTINGS</Text>
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
          <Text style={[styles.label, { color: palette.secondaryText }]}>
            DESCRIPTION (OPTIONAL)
          </Text>
          <TextInput
            accessibilityLabel="Meal description"
            multiline
            onChangeText={setDescription}
            placeholder="Chicken thighs, rice, and broccoli"
            placeholderTextColor={palette.dimText}
            style={[styles.input, { borderColor: palette.hairline, color: palette.text }]}
            value={description}
          />
          <Pressable
            accessibilityRole="button"
            disabled={!photo || working}
            onPress={() => void analyze()}
            style={[styles.primary, { backgroundColor: palette.accent, opacity: photo ? 1 : 0.45 }]}
          >
            <Text style={styles.primaryText}>{working ? "ANALYZING" : "ANALYZE PHOTO"}</Text>
          </Pressable>
        </>
      ) : (
        <>
          <View style={styles.totals}>
            <Metric label="CALORIES" value={analysis.calories} />
            <Metric label="PROTEIN" value={`${analysis.protein_g}g`} />
            <Metric label="FIBER" value={`${analysis.fiber_g}g`} />
          </View>
          {analysis.items.map((item, index) => (
            <View
              key={`${item.name}-${index}`}
              style={[styles.item, { borderColor: palette.hairline }]}
            >
              <Text style={[styles.itemName, { color: palette.text }]}>{item.name}</Text>
              <Text style={{ color: palette.secondaryText }}>{item.portion}</Text>
              <Text style={{ color: palette.dimText }}>
                {item.calories} kcal · {item.protein_g}g protein · {item.fiber_g}g fiber
              </Text>
            </View>
          ))}
          <Pressable
            accessibilityRole="button"
            disabled={working}
            onPress={() => void save()}
            style={[styles.primary, { backgroundColor: palette.accent }]}
          >
            <Text style={styles.primaryText}>{working ? "SAVING" : "SAVE TO TODAY"}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => setAnalysis(null)}
            style={styles.link}
          >
            <Text style={{ color: palette.accent }}>CHOOSE ANOTHER PHOTO</Text>
          </Pressable>
        </>
      )}
      {error ? (
        <View>
          <Text accessibilityRole="alert" style={[styles.error, { color: palette.error }]}>
            {error}
          </Text>
          <Pressable accessibilityRole="button" onPress={() => router.replace("/log-food")}>
            <Text style={{ color: palette.accent }}>USE MANUAL</Text>
          </Pressable>
        </View>
      ) : null}
    </ScrollView>
  );
}

function Action({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.action}>
      <Text style={styles.actionText}>{label}</Text>
    </Pressable>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: 48, paddingHorizontal: 24, paddingTop: 64 },
  eyebrow: { fontSize: 12, fontWeight: "800", letterSpacing: 2, marginTop: 30 },
  title: { fontSize: 36, fontWeight: "900", marginBottom: 24, marginTop: 8 },
  actions: { flexDirection: "row", gap: 12 },
  action: {
    backgroundColor: "#202326",
    borderRadius: 10,
    flex: 1,
    minHeight: 52,
    justifyContent: "center",
    alignItems: "center",
  },
  actionText: { color: "#f5f7f8", fontSize: 12, fontWeight: "900", letterSpacing: 1 },
  permission: { gap: 12, marginTop: 18 },
  photo: { borderRadius: 14, height: 260, marginTop: 22, width: "100%" },
  label: { fontSize: 11, fontWeight: "800", letterSpacing: 1.5, marginBottom: 8, marginTop: 24 },
  input: {
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 16,
    minHeight: 90,
    padding: 14,
    textAlignVertical: "top",
  },
  primary: {
    alignItems: "center",
    borderRadius: 12,
    justifyContent: "center",
    marginTop: 24,
    minHeight: 58,
  },
  primaryText: { color: "#001018", fontWeight: "900", letterSpacing: 1.2 },
  totals: { flexDirection: "row", gap: 8, marginBottom: 24 },
  metric: { backgroundColor: "#17191b", borderRadius: 10, flex: 1, padding: 12 },
  metricValue: { color: "#f5f7f8", fontSize: 22, fontWeight: "900" },
  metricLabel: { color: "#8b8f94", fontSize: 10, fontWeight: "800", marginTop: 4 },
  item: { borderBottomWidth: 1, paddingVertical: 16 },
  itemName: { fontSize: 18, fontWeight: "800", marginBottom: 4 },
  link: { alignItems: "center", minHeight: 48, justifyContent: "center" },
  error: { fontSize: 14, lineHeight: 20, marginBottom: 12, marginTop: 18 },
});
