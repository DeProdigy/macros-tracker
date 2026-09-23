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
 *
 * `keyboard` also owns the ways to close the keyboard from the page (MAC-77). A
 * tap on empty space closes it. A drag down a scrolling page closes it.
 *
 * A number pad has no Return key, so each number input also sets
 * `returnKeyType="done"`. On iOS, React Native then gives that input its own
 * native toolbar with a Done button. The input owns its toolbar, so it cannot
 * lose it.
 *
 * MAC-77 first used one shared `InputAccessoryView` for every input on the
 * screen. That was wrong on Fabric. The view binds, once, to the first input
 * with its ID when it mounts. Every later input, such as the height and weight
 * questions, got no Done button. One shared accessory view is the right choice
 * only for a screen that holds one input for its whole life.
 */

import type { ReactNode } from "react";
import {
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
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
   * Lifts the content and the footer above the keyboard, and lets the user
   * close it. Turn this on for any screen holding a TextInput.
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
      // "interactive" lets a drag pull the keyboard down with the finger, the
      // same as Messages. "handled" already closes it on a tap in empty space.
      // Only a `keyboard` screen gets the drag, so the prop keeps one meaning.
      keyboardDismissMode={keyboard ? "interactive" : "none"}
      keyboardShouldPersistTaps="handled"
      style={styles.fill}
      testID={testID}
    >
      {children}
    </ScrollView>
  ) : keyboard ? (
    // A plain View ignores a tap on empty space, so the keyboard stays up. This
    // Pressable closes it instead. Buttons and inputs inside still take their
    // own taps first, because the innermost touchable wins the responder.
    //
    // `accessible={false}` stops VoiceOver from reading the whole page as one
    // button and hiding everything inside it.
    <Pressable
      accessible={false}
      onPress={Keyboard.dismiss}
      style={[styles.fill, { paddingBottom: contentBottom }, contentStyle]}
      testID={testID}
    >
      {children}
    </Pressable>
  ) : (
    <View style={[styles.fill, { paddingBottom: contentBottom }, contentStyle]} testID={testID}>
      {children}
    </View>
  );

  const footerView = footer ? (
    <View style={[styles.footer, { paddingBottom: bottom }]}>{footer}</View>
  ) : null;

  return (
    <View style={[styles.page, { paddingTop: top }, style]}>
      {keyboard ? (
        // iOS and Android report the keyboard differently. iOS gives a frame
        // the view can pad against. Android resizes the window itself, so
        // padding it a second time pushes the content twice as far.
        //
        // The footer sits inside this view, not after it. The view pads only
        // its own children, so a footer outside it stayed under the keyboard.
        // That hid Next on every onboarding question (MAC-77).
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={styles.fill}
          testID="screen-keyboard-avoider"
        >
          {body}
          {footerView}
        </KeyboardAvoidingView>
      ) : (
        <>
          {body}
          {footerView}
        </>
      )}
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
