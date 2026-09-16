/**
 * The colours the E2 screens share.
 *
 * A placeholder for doc 12's visual system, not a replacement for it. It exists
 * because MAC-31 adds three screens beside Welcome and a fourth copy of the
 * same six hex values is how a design system quietly stops being one.
 *
 * Colours are chosen by the OS theme rather than by a setting. `automatic` in
 * app.json means the app follows the system, and a user who has committed to
 * dark mode everywhere has already answered this question.
 */

import { useColorScheme } from "react-native";

// The macro colours below arrived with MAC-58, taken from the approved Today
// screens (design/source/linear-2026-08-31/19-today-normal.png and
// 20-today-over-target.png). They are the first entries here that a mockup
// dictates rather than a developer picking. MAC-61 owns the real visual system
// and should absorb them.
//
// Each macro gets its own hue because the over-target meaning differs by macro.
// Passing the calorie target is a warning. Passing the protein target is a win.
// One "over" colour would say the same thing about both.
export const lightPalette = {
  background: "#ffffff",
  text: "#111111",
  secondaryText: "#5a5a5a",
  dimText: "#9b9b9b",
  accent: "#208aef",
  error: "#c0392b",
  hairline: "#dcdcdc",
  card: "#f4f4f5",
  ringTrack: "#e4e4e7",
  calories: "#14b8a6",
  caloriesOver: "#f59e0b",
  protein: "#a855f7",
  proteinMet: "#16a34a",
  fiber: "#a855f7",
  fiberMet: "#16a34a",
};

export type Palette = typeof lightPalette;

export const darkPalette: Palette = {
  background: "#000000",
  text: "#f5f5f5",
  secondaryText: "#a8a8a8",
  dimText: "#6b6b6b",
  accent: "#4ea3f5",
  error: "#ff6b5b",
  hairline: "#2a2a2a",
  card: "#161618",
  ringTrack: "#27272a",
  calories: "#5eead4",
  caloriesOver: "#fb923c",
  protein: "#c084fc",
  proteinMet: "#4ade80",
  fiber: "#c084fc",
  fiberMet: "#4ade80",
};

export const usePalette = (): Palette => (useColorScheme() === "dark" ? darkPalette : lightPalette);
