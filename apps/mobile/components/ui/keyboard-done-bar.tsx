/**
 * A Done button that sits on top of the iOS keyboard.
 *
 * iOS number pads have no Return key. Without this bar, a user who types their
 * age has no key that closes the keyboard (MAC-77). Native iOS apps solve this
 * with an input accessory view, which is the bar above a keyboard. React Native
 * exposes it as `InputAccessoryView`.
 *
 * The bar matches its inputs by ID, not by position. `Screen` renders one bar
 * when `keyboard` is on, and any input on that screen joins it by passing
 * `inputAccessoryViewID={KEYBOARD_DONE_ID}`. An input on a screen without the
 * bar keeps the ID and gets no bar. Nothing breaks.
 *
 * `react-native-keyboard-controller` has a richer toolbar with up and down
 * arrows. MAC-77 rejected it because it is a native module and its main gain
 * is on Android, which the MVP does not ship. Pick it when either changes.
 */

import { InputAccessoryView, Keyboard, Platform, Pressable, StyleSheet, View } from "react-native";

import { Caption } from "@/components/ui/text";
import { colors, space, tapTarget } from "@/lib/theme";

export const KEYBOARD_DONE_ID = "keyboard-done";

export function KeyboardDoneBar() {
  // `InputAccessoryView` is iOS only. Android number pads have their own
  // confirm key, and the MVP does not ship Android anyway.
  if (Platform.OS !== "ios") return null;

  return (
    <InputAccessoryView nativeID={KEYBOARD_DONE_ID}>
      <View style={styles.bar}>
        <Pressable
          accessibilityLabel="Close keyboard"
          accessibilityRole="button"
          onPress={() => Keyboard.dismiss()}
          style={styles.done}
        >
          <Caption color={colors.accent}>DONE</Caption>
        </Pressable>
      </View>
    </InputAccessoryView>
  );
}

const styles = StyleSheet.create({
  bar: {
    alignItems: "flex-end",
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderTopWidth: 1,
    paddingHorizontal: space.xl,
  },
  done: { justifyContent: "center", minHeight: tapTarget, paddingHorizontal: space.md },
});
