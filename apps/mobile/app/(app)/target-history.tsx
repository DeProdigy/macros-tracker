import { listTargets, type TargetVersion, type TargetVersionSourceEnum } from "@macros/api-client";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { usePalette, type Palette } from "@/lib/palette";

const parseDate = (date: string) => {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
};

const displayDate = (date: string) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  })
    .format(parseDate(date))
    .toUpperCase();

// Keep this exhaustive. If the API adds a source, TypeScript makes this screen
// choose honest copy instead of silently calling the new source Manual.
const SOURCE_LABELS: Record<TargetVersionSourceEnum, string> = {
  onboarding: "ONBOARDING",
  manual: "MANUAL",
};

export default function TargetHistoryScreen() {
  const palette = usePalette();
  const router = useRouter();
  const [versions, setVersions] = useState<TargetVersion[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    setVersions(null);
    try {
      const response = await listTargets();
      if (response.status !== 200) {
        throw new Error(`Unexpected target list status: ${response.status}`);
      }
      setVersions(response.data);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      style={[styles.container, { backgroundColor: palette.background }]}
    >
      <Pressable accessibilityRole="button" onPress={() => router.back()}>
        <Text style={[styles.back, { color: palette.secondaryText }]}>‹ Settings</Text>
      </Pressable>

      <Text style={[styles.title, { color: palette.text }]}>Target history</Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        Every change writes a version. Days already logged keep the targets that were live at the
        time.
      </Text>

      {versions === null && !failed ? (
        <View
          accessibilityLabel="Loading target history"
          style={[styles.state, { borderColor: palette.hairline }]}
        >
          <ActivityIndicator color={palette.accent} />
        </View>
      ) : failed ? (
        <View style={[styles.state, { borderColor: palette.hairline }]}>
          <Text style={[styles.stateTitle, { color: palette.text }]}>
            Target history did not load.
          </Text>
          <Text style={[styles.stateBody, { color: palette.secondaryText }]}>
            Nothing on this screen changed. Try again when the connection is ready.
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => void load()}
            style={[styles.retry, { backgroundColor: palette.accent }]}
          >
            <Text style={styles.retryLabel}>TRY AGAIN</Text>
          </Pressable>
        </View>
      ) : versions?.length === 0 ? (
        <View style={[styles.state, { borderColor: palette.hairline }]}>
          <Text style={[styles.stateTitle, { color: palette.text }]}>No target versions yet.</Text>
          <Text style={[styles.stateBody, { color: palette.secondaryText }]}>
            Your first saved targets will appear here.
          </Text>
        </View>
      ) : (
        versions?.map((version) => (
          <VersionCard key={version.id} version={version} palette={palette} />
        ))
      )}
    </ScrollView>
  );
}

const VersionCard = ({ version, palette }: { version: TargetVersion; palette: Palette }) => (
  <View style={[styles.card, { backgroundColor: palette.hairline }]}>
    <View style={styles.cardHeader}>
      <Text style={[styles.date, { color: palette.text }]}>
        EFFECTIVE {displayDate(version.effective_from)}
      </Text>
      <Text style={[styles.source, { color: palette.secondaryText }]}>
        {SOURCE_LABELS[version.source]}
      </Text>
    </View>
    <View style={styles.metrics}>
      <Metric value={version.calories} unit="KCAL" color={palette.accent} />
      <Metric value={version.protein_g} unit="P" color="#70e6a3" />
      <Metric value={version.fiber_g} unit="F" color="#ad8cff" />
    </View>
    {version.rationale ? (
      <Text style={[styles.rationale, { color: palette.secondaryText }]}>{version.rationale}</Text>
    ) : null}
  </View>
);

const Metric = ({ value, unit, color }: { value: number; unit: string; color: string }) => (
  <Text style={[styles.metric, { color }]}>
    {value.toLocaleString()} <Text style={styles.unit}>{unit}</Text>
  </Text>
);

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { gap: 20, paddingBottom: 64, paddingHorizontal: 24, paddingTop: 56 },
  back: { fontSize: 15, letterSpacing: 1, textTransform: "uppercase" },
  title: { fontSize: 34, fontWeight: "800", letterSpacing: -0.7 },
  body: { fontSize: 16, lineHeight: 24 },
  state: {
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    gap: 10,
    minHeight: 180,
    justifyContent: "center",
    padding: 20,
  },
  stateTitle: { fontSize: 18, fontWeight: "700" },
  stateBody: { fontSize: 14, lineHeight: 21 },
  retry: { alignItems: "center", borderRadius: 10, marginTop: 8, paddingVertical: 13 },
  retryLabel: { color: "#06131a", fontSize: 14, fontWeight: "800", letterSpacing: 1 },
  card: { borderRadius: 14, gap: 16, padding: 18 },
  cardHeader: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  date: { fontSize: 13, letterSpacing: 1.5 },
  source: { fontSize: 11, letterSpacing: 1.2 },
  metrics: { flexDirection: "row", gap: 18 },
  metric: { fontSize: 23, fontWeight: "800" },
  unit: { color: "#6b6b6b", fontSize: 11, fontWeight: "400" },
  rationale: { fontSize: 14, lineHeight: 21 },
});
