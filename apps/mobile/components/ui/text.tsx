/**
 * Text that already knows its font, its size, and its colour.
 *
 * Before this file the app had 22 distinct `fontSize` values across 18 screens.
 * Nobody chose 22. It is what happens when each screen picks a number in
 * isolation and 13 versus 14 never looks wrong on its own.
 *
 * The fix is to stop passing sizes. A screen asks for a `Title` or a `Label`,
 * and the seven roles in `lib/theme.ts` decide the rest. This is the same idea
 * as a heading level in HTML: the name says what the text is for, and the
 * stylesheet says what that looks like.
 *
 * When this is the wrong pattern: a component library that other teams style
 * differently needs the escape hatch to be the main road, not the exception.
 * Here there is one app and one design, so the exception stays an exception.
 * `style` is still accepted for the genuine one-off, such as a colour that
 * depends on whether a number passed its target.
 */

import { Text as RNText, type TextProps, type TextStyle } from "react-native";

import { colors, numeralScaleCap, type, type TypeRole } from "@/lib/theme";

type Props = TextProps & {
  /** Overrides the role's default colour. Most callers leave this alone. */
  color?: string;
};

/**
 * Roles that hold a number inside fixed geometry.
 *
 * These get a Dynamic Type ceiling. Everything else scales without a limit,
 * because capping a sentence is how an accessibility setting stops working for
 * the person who needs it.
 */
const CAPPED_ROLES: ReadonlySet<TypeRole> = new Set<TypeRole>(["display", "numeral"]);

const build = (role: TypeRole, defaultColor: string) => {
  const Component = ({ color, style, ...rest }: Props) => (
    <RNText
      maxFontSizeMultiplier={CAPPED_ROLES.has(role) ? numeralScaleCap : undefined}
      style={[type[role] as TextStyle, { color: color ?? defaultColor }, style]}
      {...rest}
    />
  );

  Component.displayName = role;
  return Component;
};

/** The calorie number inside the ring. */
export const Display = build("display", colors.text);

/** A screen title. */
export const Title = build("title", colors.text);

/** A section or card title. */
export const Heading = build("heading", colors.text);

/** A tile value, such as grams of protein eaten. */
export const Numeral = build("numeral", colors.text);

/** A tagline or a standfirst under a title. Grey by default. */
export const Lead = build("lead", colors.textSecondary);

/** Sentences, entry names, and button text. */
export const Body = build("body", colors.text);

/** A support sentence under a heading, or a hint under an input. */
export const Muted = build("body", colors.textSecondary);

/**
 * An uppercase label above a value.
 *
 * The caller passes the text already uppercased rather than relying on
 * `textTransform`. A screen reader reads "PROTEIN" as an initialism in some
 * voices, so the visual choice and the spoken one need to stay separable. A
 * screen that needs both passes an `accessibilityLabel`.
 */
export const Label = build("label", colors.textSecondary);

/** A time, a date, or a metric string beside an entry. */
export const Caption = build("caption", colors.textSecondary);

/** An error sentence. Always paired with `accessibilityRole="alert"`. */
export const ErrorText = ({ style, ...rest }: TextProps) => (
  <RNText
    accessibilityRole="alert"
    style={[type.body as TextStyle, { color: colors.error }, style]}
    {...rest}
  />
);
