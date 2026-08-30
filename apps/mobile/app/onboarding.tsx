/**
 * The third outcome of the launch gate, standing in for the six questions.
 *
 * **Onboarding is a hard gate.** Ruled 30 Aug 2026, reversing the 20 Aug
 * sequencing. The questions come first, the first meal comes after, and there
 * is no skip. So this screen has no way out, which is the correct shape and an
 * uncomfortable one while the questions do not exist.
 *
 * It had a *Not now* button until MAC-47. That button wrote nothing and lasted
 * one launch, and the fix for it was briefly a whole `onboarding_skipped_at`
 * column before the sequencing decision removed the reason for either.
 *
 * MAC-50 makes this screen completable by hand. MAC-42 replaces it with the six
 * questions. Until MAC-50 lands, a new user has no route into the app, which is
 * a real cost of the reversal and is written down rather than worked around.
 */

import { Redirect } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function OnboardingPlaceholder() {
  const session = useSession();
  const palette = usePalette();

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
        Targets come first. Nothing logs until they exist, so there is no way past this screen yet.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, gap: 12, justifyContent: "center", paddingHorizontal: 32 },
  title: { fontSize: 28, fontWeight: "700", letterSpacing: -0.5 },
  body: { fontSize: 16, lineHeight: 23 },
});
