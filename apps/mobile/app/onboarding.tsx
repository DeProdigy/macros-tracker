/**
 * The third outcome of the launch gate, standing in for E3.
 *
 * A signed-in user who has not set targets is a real, supported state — doc 26
 * made the onboarding stack exitable precisely so that logging can happen
 * before any question is answered. The gate has to route them somewhere, and
 * routing them to Today would be a lie the moment E3 lands and starts expecting
 * this route to exist.
 *
 * So: a placeholder that names what is missing and offers the exit doc 26
 * insists on. MAC-36 onwards replaces it with 9d, 9e and 9f.
 */

import { Redirect, useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function OnboardingPlaceholder() {
  const session = useSession();
  const palette = usePalette();
  const router = useRouter();

  if (session.status === "loading") {
    return null;
  }

  // Outside the (app) group, so this route carries its own guard.
  if (session.status === "signedOut") {
    return <Redirect href="/login" />;
  }

  return (
    <View style={[styles.container, { backgroundColor: palette.background }]}>
      <Text style={[styles.title, { color: palette.text }]}>Set your targets</Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        Six questions turn into a calorie and macro target. That flow is E3 and is not built yet.
      </Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        Skipping is fine and always will be. Meals still log without targets. Nothing gets scored
        until they exist.
      </Text>

      <Pressable
        accessibilityRole="button"
        onPress={() => router.replace("/today")}
        style={[styles.button, { borderColor: palette.hairline }]}
      >
        <Text style={[styles.buttonLabel, { color: palette.text }]}>Not now</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, gap: 12, justifyContent: "center", paddingHorizontal: 32 },
  title: { fontSize: 28, fontWeight: "700", letterSpacing: -0.5 },
  body: { fontSize: 16, lineHeight: 23 },
  button: {
    alignItems: "center",
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    marginTop: 16,
    paddingVertical: 14,
  },
  buttonLabel: { fontSize: 16, fontWeight: "600" },
});
