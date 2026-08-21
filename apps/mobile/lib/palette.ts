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

export const lightPalette = {
  background: "#ffffff",
  text: "#111111",
  secondaryText: "#5a5a5a",
  dimText: "#9b9b9b",
  accent: "#208aef",
  error: "#c0392b",
  hairline: "#dcdcdc",
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
};

export const usePalette = (): Palette => (useColorScheme() === "dark" ? darkPalette : lightPalette);
