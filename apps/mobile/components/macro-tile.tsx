/**
 * A protein or fiber tile from the approved Today screens.
 *
 * Deliberately not shared with the calorie ring. The two look related and mean
 * opposite things: passing the calorie target is a warning, passing the protein
 * target is the goal. A single component with an `isCalories` flag would put
 * that contradiction inside one set of branches.
 */

import { StyleSheet, Text, View } from "react-native";

import type { MacroProgress } from "@/lib/day-progress";
import { usePalette } from "@/lib/palette";

type Props = {
  label: string;
  progress: MacroProgress;
  /** Colour while the target is still ahead. */
  color: string;
  /** Colour once the target is reached or passed. */
  metColor: string;
};

export function MacroTile({ label, progress, color, metColor }: Props) {
  const palette = usePalette();
  const met = progress.status !== "under";
  const barColor = met ? metColor : color;
  const consumed = Math.round(progress.consumed);
  const target = Math.round(progress.target);
  const short = Math.round(progress.remaining);
  const footer = met ? "TARGET MET" : `${short}g short`;

  return (
    <View
      accessibilityLabel={`${label}. ${consumed} of ${target} grams. ${met ? "Target met." : `${short} grams short.`}`}
      accessibilityRole="progressbar"
      accessibilityValue={{ min: 0, max: target, now: Math.min(consumed, target) }}
      style={[styles.tile, { backgroundColor: palette.card }]}
    >
      <Text style={[styles.label, { color: palette.secondaryText }]}>{label.toUpperCase()}</Text>
      <View style={styles.row}>
        <Text style={[styles.value, { color: barColor }]}>{consumed}</Text>
        <Text style={[styles.target, { color: palette.dimText }]}>/{target}g</Text>
      </View>
      <View style={[styles.track, { backgroundColor: palette.ringTrack }]}>
        <View
          style={[
            styles.fill,
            { backgroundColor: barColor, width: `${Math.round(progress.fraction * 100)}%` },
          ]}
        />
      </View>
      <Text style={[styles.footer, { color: met ? metColor : palette.secondaryText }]}>
        {footer}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tile: { borderRadius: 14, flex: 1, gap: 8, padding: 16 },
  label: { fontSize: 12, letterSpacing: 2 },
  row: { alignItems: "baseline", flexDirection: "row", gap: 4 },
  value: { fontSize: 30, fontWeight: "700" },
  target: { fontSize: 15 },
  track: { borderRadius: 2, height: 4, overflow: "hidden" },
  fill: { height: 4 },
  footer: { fontSize: 13 },
});
