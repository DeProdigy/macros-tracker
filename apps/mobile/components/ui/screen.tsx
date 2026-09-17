/**
 * The page wrapper that handles the notch, the home indicator, and the
 * keyboard.
 *
 * Before this, no file in the app read a safe-area inset. `today.tsx` wrote
 * `paddingTop: 68` and `bottom: 34` and hoped. Those two numbers are correct on
 * one iPhone and wrong on every other one, and they are wrong in a way that
 * only shows up on hardware, which is the expensive kind of wrong.
 *
 * `react-native-safe-area-context` reports the real insets per device. The
 * wrapper exists rather than a `useSafeAreaInsets()` call in each screen for
 * one reason: a screen written six months from now cannot forget a wrapper it
 * has to use to render anything. It can very easily forget a hook.
 *
 * The escape hatch is `edges`. The camera screen wants its preview to run under
 * the notch, so it passes `edges={["bottom"]}` and takes the top itself.
 */

import type { ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors } from "@/lib/theme";

type Edge = "top" | "bottom";

type Props = {
  /**
   * Optional so a screen can render an empty page while it loads. That is not
   * a blank frame: the page still paints the app's background, which is what
   * stops a white flash before the real content arrives.
   */
  children?: ReactNode;
  /** Wraps the content in a ScrollView. Off for screens that must not scroll. */
  scroll?: boolean;
  /**
   * Lifts the content above the keyboard. Turn this on for any screen holding
   * a TextInput.
   */
  keyboard?: boolean;
  /** Which insets to apply. Both by default. */
  edges?: readonly Edge[];
  /** A sticky action pinned above the home indicator, such as LOG FOOD. */
  footer?: ReactNode;
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
  testID?: string;
};

const DEFAULT_EDGES: readonly Edge[] = ["top", "bottom"];

export function Screen({
  children,
  scroll = false,
  keyboard = false,
  edges = DEFAULT_EDGES,
  footer,
  style,
  contentStyle,
  testID,
}: Props) {
  const insets = useSafeAreaInsets();
  const top = edges.includes("top") ? insets.top : 0;
  const bottom = edges.includes("bottom") ? insets.bottom : 0;

  // A footer owns the bottom inset instead of the content, or the two both pad
  // for the home indicator and the gap doubles.
  const contentBottom = footer ? 0 : bottom;

  const body = scroll ? (
    <ScrollView
      contentContainerStyle={[{ paddingBottom: contentBottom }, contentStyle]}
      keyboardShouldPersistTaps="handled"
      style={styles.fill}
      testID={testID}
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.fill, { paddingBottom: contentBottom }, contentStyle]} testID={testID}>
      {children}
    </View>
  );

  return (
    <View style={[styles.page, { paddingTop: top }, style]}>
      {keyboard ? (
        // iOS and Android report the keyboard differently. iOS gives a frame
        // the view can pad against. Android resizes the window itself, so
        // padding it a second time pushes the content twice as far.
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={styles.fill}
        >
          {body}
        </KeyboardAvoidingView>
      ) : (
        body
      )}
      {footer ? <View style={[styles.footer, { paddingBottom: bottom }]}>{footer}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  // The footer sits in normal flow rather than absolutely, so content above it
  // can never scroll underneath and hide its last row.
  footer: { flexShrink: 0 },
  page: { backgroundColor: colors.background, flex: 1 },
});
