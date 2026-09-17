/**
 * The one place that owns a colour, a size, or a distance.
 *
 * This replaces `lib/palette.ts`, which held six colours and an OS-theme
 * switch. The switch is gone because MAC-61 made the app dark only. Every one
 * of the 46 approved mockups is dark, no light artwork was ever drawn, and a
 * light palette nobody designed is guesswork that still costs a second contrast
 * check on every change.
 *
 * The values below are measured, not chosen. I sampled the dominant colours out
 * of design/source/linear-2026-08-31/19-today-normal.png, 20-today-over-target
 * .png, 01-auth-welcome.png, 12-log-review.png, 05-onboarding-question.png, and
 * 37-settings.png. That matters more than it sounds: the previous palette mixed
 * four sampled colours with eight a developer picked, and the picked ones drift.
 *
 * The pattern is design tokens. Name the job, not the value. A component asks
 * for `colors.warning`, never for `#ffa24d`, so the day the warning colour
 * changes is a one-line day. It is the wrong pattern when a project has one
 * screen, or when a component genuinely needs a one-off colour that means
 * nothing elsewhere. Neither is true here: 18 screens held 32 loose hex codes
 * between them before this file existed.
 */

import {
  Archivo_400Regular,
  Archivo_500Medium,
  Archivo_700Bold,
  Archivo_800ExtraBold,
} from "@expo-google-fonts/archivo";
import { IBMPlexMono_400Regular, IBMPlexMono_500Medium } from "@expo-google-fonts/ibm-plex-mono";
import type { TextStyle } from "react-native";

/**
 * Every colour the app is allowed to draw.
 *
 * Read the second column of the table in plans/tickets/MAC-61.md for where each
 * one came from. The names describe a job. `surface` is "the thing a card sits
 * on", not "dark grey", so a component reading it still makes sense if the grey
 * changes.
 */
export const colors = {
  /** The page. True black, as the canonical visual direction asks for. */
  background: "#000000",
  /** Cards, tiles, and list rows. */
  surface: "#0e1013",
  /** A card on a card, and the fill behind a text input. */
  surfaceRaised: "#1b1e23",
  /** Hairlines, dividers, and input outlines. */
  border: "#242628",

  /** Primary text and numerals. 21:1 on the background. */
  text: "#ffffff",
  /** Labels, units, and support sentences. 6.48:1 on the background. */
  textSecondary: "#8b8f98",
  /**
   * Disabled controls, decoration, and entry timestamps.
   *
   * 2.51:1 on the background, which fails WCAG AA for body text. Alex chose the
   * artwork over the standard on 17 Sep 2026 and the mockups put this grey on
   * entry timestamps. The exemption is deliberate and recorded. Do not spread
   * it to any other text that carries meaning.
   */
  textDim: "#4a4e55",

  /** Cyan primary. Calories, links, and the primary button. */
  accent: "#5ee7e0",
  /** The calorie ring track, and any tinted fill behind the accent. */
  accentDim: "#265151",

  /** Calories over target. Never used for protein or fiber. */
  warning: "#ffa24d",
  /** The tinted panel behind an over-target day. */
  warningSurface: "#1a1108",
  /** A gram target reached. Passing a gram target is the goal, not a warning. */
  positive: "#7beba4",
  /** Protein while its target is still ahead. */
  protein: "#b79cff",
  /** A failed request or a rejected value. */
  error: "#ff6b5b",
} as const;

/**
 * Six steps, and two larger ones for page rhythm.
 *
 * The 18 screens used 30 distinct padding, margin, and gap values between them.
 * Most of the difference was invisible: nobody sees 13 against 14. A short
 * scale removes the decision rather than the pixel.
 */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  /** The gap between a screen's last control and the section above it. */
  section: 48,
  /** Vertical breathing room inside an empty state. */
  empty: 64,
} as const;

/** Three radii replace seven. 8 for small chips, 12 for cards, 16 for sheets. */
export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  /** A circle. Use with equal width and height. */
  full: 9999,
} as const;

/** The horizontal gutter every screen shares. */
export const gutter = space.xl;

/**
 * The smallest square iOS calls a comfortable touch. Apple's Human Interface
 * Guidelines set it, and the ticket's acceptance criteria repeat it.
 */
export const tapTarget = 44;

/**
 * The font families, keyed by the names `useFonts` registers them under.
 *
 * `expo-font` maps whatever key you give it to a `fontFamily` string. Using the
 * package's own export names as keys keeps one spelling in play instead of two.
 */
export const fontFamily = {
  regular: "Archivo_400Regular",
  medium: "Archivo_500Medium",
  bold: "Archivo_700Bold",
  black: "Archivo_800ExtraBold",
  mono: "IBMPlexMono_400Regular",
  monoMedium: "IBMPlexMono_500Medium",
} as const;

/**
 * The font files the root layout loads before it drops the splash.
 *
 * Six weights, not eighteen. Each one is a real file in the bundle, so an
 * unused weight is dead download.
 */
export const fontAssets = {
  Archivo_400Regular,
  Archivo_500Medium,
  Archivo_700Bold,
  Archivo_800ExtraBold,
  IBMPlexMono_400Regular,
  IBMPlexMono_500Medium,
};

/**
 * Seven roles replace 22 font sizes.
 *
 * Archivo carries UI text and numerals. IBM Plex Mono carries labels, units,
 * dates, times, and metric strings. That split comes from the canonical visual
 * direction, and it is the reason the numbers on Today line up in a column: a
 * monospaced digit is always the same width.
 *
 * `letterSpacing` only appears on the two mono roles. Tracking uppercase text
 * is what makes a label read as a label rather than as a shouted sentence.
 */
export const type = {
  /** The calorie number inside the ring. One per screen, at most. */
  display: {
    fontFamily: fontFamily.black,
    fontSize: 52,
  },
  /** A screen title. */
  title: {
    fontFamily: fontFamily.black,
    fontSize: 34,
  },
  /** A section or card title. */
  heading: {
    fontFamily: fontFamily.bold,
    fontSize: 22,
  },
  /** A tile value, such as grams of protein eaten. */
  numeral: {
    fontFamily: fontFamily.bold,
    fontSize: 30,
  },
  /**
   * A tagline or a standfirst under a title.
   *
   * Added in PR 2, not PR 1. The Welcome and first-food mockups both put a
   * grey sentence under the title that is clearly larger than body text and is
   * not a heading. Body at 16 read too small under a 34-point title, and
   * `heading` is bold, which is wrong for a sentence. That gap only showed up
   * once the scale met a real screen.
   */
  lead: {
    fontFamily: fontFamily.regular,
    fontSize: 20,
  },
  /** Sentences, entry names, and button text. */
  body: {
    fontFamily: fontFamily.regular,
    fontSize: 16,
  },
  /** An uppercase label above a value. */
  label: {
    fontFamily: fontFamily.monoMedium,
    fontSize: 12,
    letterSpacing: 1.5,
  },
  /** A time, a date, or a metric string beside an entry. */
  caption: {
    fontFamily: fontFamily.mono,
    fontSize: 13,
    letterSpacing: 0.5,
  },
} as const satisfies Record<string, TextStyle>;

export type TypeRole = keyof typeof type;

/**
 * The ceiling on iOS Dynamic Type, for text that sits in fixed geometry.
 *
 * React Native scales text by the user's system setting by default, and that
 * default is correct for prose. It is wrong for the 52-point number inside a
 * ring, because at the largest accessibility size the number leaves the ring.
 *
 * 1.4 is the compromise. It honours the first few steps of the setting, which
 * is where most users who change it actually sit, and it stops short of the
 * sizes that break the layout. Never put this on a sentence.
 */
export const numeralScaleCap = 1.4;
