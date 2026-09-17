import { listTargets, type TargetVersion, type TargetVersionSourceEnum } from "@macros/api-client";
import { useRouter } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Caption, Heading, Label, Muted, Numeral, Title } from "@/components/ui/text";

import { colors, radius, space, tapTarget, type } from "@/lib/theme";

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
    <Screen contentStyle={styles.content} scroll>
      <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
        <Label>‹ SETTINGS</Label>
      </Pressable>

      <Title>Target history</Title>
      <Muted style={styles.body}>
        Every change writes a version. Days already logged keep the targets that were live at the
        time.
      </Muted>

      {versions === null && !failed ? (
        <View accessibilityLabel="Loading target history" style={styles.state}>
          <ActivityIndicator color={colors.accent} />
        </View>
      ) : failed ? (
        <View style={styles.state}>
          <Heading>Target history did not load.</Heading>
          <Muted style={styles.stateBody}>
            Nothing on this screen changed. Try again when the connection is ready.
          </Muted>
          <Button onPress={() => void load()} style={styles.retry} title="Try again" />
        </View>
      ) : versions?.length === 0 ? (
        <View style={styles.state}>
          <Heading>No target versions yet.</Heading>
          <Muted style={styles.stateBody}>Your first saved targets will appear here.</Muted>
        </View>
      ) : (
        versions?.map((version) => <VersionCard key={version.id} version={version} />)
      )}
    </Screen>
  );
}

const VersionCard = ({ version }: { version: TargetVersion }) => (
  <View style={styles.card}>
    <View style={styles.cardHeader}>
      <Label color={colors.text}>EFFECTIVE {displayDate(version.effective_from)}</Label>
      <Label>{SOURCE_LABELS[version.source]}</Label>
    </View>
    <View style={styles.metrics}>
      <Metric value={version.calories} unit="KCAL" color={colors.accent} />
      <Metric value={version.protein_g} unit="P" color={colors.positive} />
      <Metric value={version.fiber_g} unit="F" color={colors.protein} />
    </View>
    {version.rationale ? <Muted style={styles.rationale}>{version.rationale}</Muted> : null}
  </View>
);

const Metric = ({ value, unit, color }: { value: number; unit: string; color: string }) => (
  <Numeral color={color} style={styles.metric}>
    {value.toLocaleString()} <Caption color={colors.textDim}>{unit}</Caption>
  </Numeral>
);

const styles = StyleSheet.create({
  back: { justifyContent: "center", minHeight: tapTarget },
  body: { lineHeight: 24 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    gap: space.lg,
    padding: space.lg,
  },
  cardHeader: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  content: {
    gap: space.xl,
    paddingBottom: space.empty,
    paddingHorizontal: space.xl,
    paddingTop: space.lg,
  },
  metric: { fontSize: type.heading.fontSize },
  metrics: { flexDirection: "row", gap: space.lg },
  rationale: { fontSize: type.caption.fontSize, lineHeight: 21 },
  retry: { marginTop: space.sm },
  state: {
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: space.sm,
    justifyContent: "center",
    minHeight: 180,
    padding: space.xl,
  },
  stateBody: { fontSize: type.caption.fontSize, lineHeight: 21 },
});
