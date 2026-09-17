/**
 * A protein or fiber tile from the approved Today screens.
 *
 * Deliberately not shared with the calorie ring. The two look related and mean
 * opposite things: passing the calorie target is a warning, passing the protein
 * target is the goal. A single component with an `isCalories` flag would put
 * that contradiction inside one set of branches.
 */

import { StyleSheet, View } from "react-native";

import { Caption, Label, Numeral } from "@/components/ui/text";
import type { MacroProgress } from "@/lib/day-progress";
import { colors, radius, space } from "@/lib/theme";

type Props = {
  label: string;
  progress: MacroProgress;
  /** Colour while the target is still ahead. */
  color: string;
  /** Colour once the target is reached or passed. */
  metColor: string;
};

export function MacroTile({ label, progress, color, metColor }: Props) {
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
      style={styles.tile}
    >
      <Label>{label.toUpperCase()}</Label>
      <View style={styles.row}>
        <Numeral color={barColor}>{consumed}</Numeral>
        <Caption color={colors.textDim}>/{target}g</Caption>
      </View>
      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            { backgroundColor: barColor, width: `${Math.round(progress.fraction * 100)}%` },
          ]}
        />
      </View>
      <Caption color={met ? metColor : colors.textSecondary}>{footer}</Caption>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { height: 4 },
  row: { alignItems: "baseline", flexDirection: "row", gap: space.xs },
  tile: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    flex: 1,
    gap: space.sm,
    padding: space.lg,
  },
  track: { backgroundColor: colors.accentDim, borderRadius: 2, height: 4, overflow: "hidden" },
});
