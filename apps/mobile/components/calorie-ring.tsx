/**
 * The remaining-calorie ring from the approved Today screens.
 *
 * Drawn with react-native-svg rather than rotated Views. The over-target state
 * needs two concentric arcs, and the View trick (two half circles, each rotated
 * behind an overflow-hidden parent) costs about eighty lines of geometry per
 * ring and cannot be read by anyone later. A native dependency is the cheaper
 * total, and Expo ships a supported version.
 *
 * An SVG arc here is a circle with a dash pattern, not a path. One dash as long
 * as the fraction you want, one gap covering the rest, rotated so the gap starts
 * at twelve o'clock. Changing the dash length is the whole animation surface if
 * MAC-61 wants one later.
 */

import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle, G } from "react-native-svg";

import type { DayProgress } from "@/lib/day-progress";
import { usePalette } from "@/lib/theme";

const SIZE = 220;
const STROKE = 16;
// The overage arc sits inside the main ring with a gap between them, which is
// what makes it read as a second lap rather than as a thicker single ring.
const INNER_INSET = STROKE + 10;

type Props = { progress: DayProgress };

function Arc({
  radius,
  color,
  fraction,
  stroke,
}: {
  radius: number;
  color: string;
  fraction: number;
  stroke: number;
}) {
  const circumference = 2 * Math.PI * radius;
  return (
    <Circle
      cx={SIZE / 2}
      cy={SIZE / 2}
      fill="none"
      r={radius}
      stroke={color}
      strokeDasharray={`${circumference * fraction} ${circumference}`}
      strokeLinecap="round"
      strokeWidth={stroke}
    />
  );
}

export function CalorieRing({ progress }: Props) {
  const palette = usePalette();
  const { calories, caloriesOverFraction } = progress;
  const over = calories.status === "over";
  const ringColor = over ? palette.caloriesOver : palette.calories;
  const radius = (SIZE - STROKE) / 2;
  const innerRadius = radius - INNER_INSET;

  const headline = over ? "OVER BY" : "REMAINING";
  const amount = Math.round(Math.abs(calories.remaining));
  const consumed = Math.round(calories.consumed);
  const target = Math.round(calories.target);

  return (
    <View
      accessibilityLabel={
        over
          ? `Over calorie target by ${amount} kcal. ${consumed} of ${target}.`
          : `${amount} kcal left. ${consumed} of ${target}.`
      }
      accessibilityRole="progressbar"
      // The label carries the meaning, "over by" against "left". The value
      // carries the position, which is what a screen reader turns into a
      // percentage. `now` clamps to `max` because a progressbar reading 113%
      // is not a thing assistive tech can say usefully.
      accessibilityValue={{ min: 0, max: target, now: Math.min(consumed, target) }}
      style={styles.wrap}
    >
      <Svg height={SIZE} width={SIZE}>
        {/* Rotate the whole drawing so a dash starts at twelve o'clock. An SVG
            circle starts at three o'clock, which reads as a quarter already
            spent. */}
        <G rotation={-90} origin={`${SIZE / 2}, ${SIZE / 2}`}>
          <Arc color={palette.ringTrack} fraction={1} radius={radius} stroke={STROKE} />
          <Arc color={ringColor} fraction={calories.fraction} radius={radius} stroke={STROKE} />
          {over ? (
            <>
              <Arc
                color={palette.ringTrack}
                fraction={1}
                radius={innerRadius}
                stroke={STROKE / 2}
              />
              <Arc
                color={ringColor}
                fraction={caloriesOverFraction}
                radius={innerRadius}
                stroke={STROKE / 2}
              />
            </>
          ) : null}
        </G>
      </Svg>
      <View pointerEvents="none" style={styles.center}>
        <Text style={[styles.headline, { color: over ? ringColor : palette.secondaryText }]}>
          {headline}
        </Text>
        <Text style={[styles.amount, { color: ringColor }]}>{amount.toLocaleString()}</Text>
        <Text style={[styles.unit, { color: palette.text }]}>{over ? "KCAL" : "KCAL LEFT"}</Text>
        <Text style={[styles.detail, { color: palette.dimText }]}>
          {consumed.toLocaleString()} of {target.toLocaleString()} kcal
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", alignSelf: "center", justifyContent: "center" },
  center: {
    alignItems: "center",
    bottom: 0,
    justifyContent: "center",
    left: 0,
    position: "absolute",
    right: 0,
    top: 0,
  },
  headline: { fontSize: 13, letterSpacing: 2 },
  // The number is the reason the screen exists, so it stays large. It does not
  // scale with Dynamic Type, because a ring cannot grow with it and a clipped
  // number is worse than a fixed one. The label under it does scale.
  amount: { fontSize: 52, fontWeight: "700" },
  unit: { fontSize: 13, letterSpacing: 2 },
  detail: { fontSize: 13, marginTop: 6 },
});
