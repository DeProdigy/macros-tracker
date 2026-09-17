/**
 * The three buttons the MVP needs.
 *
 * The app had a primary button written out longhand in six screens. Each copy
 * set its own height, radius, and letter spacing, and each copy was a chance to
 * drop the accessibility role. Two of them did.
 *
 * `variant` covers primary, secondary, and destructive. That is deliberately
 * fewer knobs than a general button component would take. A `size` prop and a
 * `color` prop would let a screen build a button that is not in the design, and
 * the point of this file is that it cannot.
 */

import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { colors, fontFamily, radius, space, tapTarget, type } from "@/lib/theme";

type Variant = "primary" | "secondary" | "destructive";

type Props = Omit<PressableProps, "style" | "children"> & {
  /** The visible text. Uppercased for primary, as the mockups draw it. */
  title: string;
  variant?: Variant;
  /** Swaps the label for a spinner and blocks presses. */
  busy?: boolean;
  style?: StyleProp<ViewStyle>;
};

const FILL: Record<Variant, string> = {
  primary: colors.accent,
  secondary: colors.surfaceRaised,
  destructive: "transparent",
};

const LABEL: Record<Variant, string> = {
  // Black on cyan reaches 13.98:1. The cyan is bright enough that white text
  // on it would fail.
  primary: colors.background,
  secondary: colors.text,
  destructive: colors.error,
};

export function Button({
  title,
  variant = "primary",
  busy = false,
  disabled,
  style,
  ...rest
}: Props) {
  const blocked = disabled === true || busy;
  const label = variant === "primary" ? title.toUpperCase() : title;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ busy, disabled: blocked }}
      disabled={blocked}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: FILL[variant],
          borderColor: variant === "destructive" ? colors.error : "transparent",
          borderWidth: variant === "destructive" ? 1 : 0,
          // Dimming on press is the only feedback a flat button gets. Without
          // it a slow request looks like a missed tap, and the user taps again.
          opacity: blocked ? 0.4 : pressed ? 0.7 : 1,
        },
        style,
      ]}
      {...rest}
    >
      {busy ? (
        <ActivityIndicator color={LABEL[variant]} />
      ) : (
        <Text
          // The label must not wrap. Capping the scale here is the lesser evil
          // against a two-line button, and the text is short enough that the
          // cap rarely bites.
          maxFontSizeMultiplier={1.6}
          numberOfLines={1}
          style={[
            styles.label,
            {
              color: LABEL[variant],
              letterSpacing: variant === "primary" ? 1.2 : 0,
            },
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    borderRadius: radius.md,
    justifyContent: "center",
    // 56 rather than the 44-point floor. 44 is the smallest comfortable tap,
    // not the right size for the main action on a screen.
    minHeight: Math.max(tapTarget, 56),
    paddingHorizontal: space.lg,
  },
  label: {
    ...type.body,
    fontFamily: fontFamily.black,
  },
});
