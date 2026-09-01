import { Redirect, router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { needsOnboarding } from "@/lib/onboarding";
import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

/** The mandatory handoff from saved targets to the first logging slice. */
export default function FirstFoodPrompt() {
  const session = useSession();
  const palette = usePalette();

  if (session.status === "loading") return null;
  if (session.status === "signedOut") return <Redirect href="/login" />;
  if (needsOnboarding(session.user)) return <Redirect href="/onboarding" />;

  return (
    <View style={[styles.container, { backgroundColor: palette.background }]}>
      <Text style={[styles.eyebrow, { color: palette.accent }]}>TARGETS SAVED</Text>
      <Text style={[styles.title, { color: palette.text }]}>Now log your first food.</Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        Your targets are ready. Your first entry will start filling the day.
      </Text>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push("./(app)/log-food")}
        style={[styles.button, { backgroundColor: palette.accent }]}
      >
        <Text style={[styles.buttonLabel, { color: palette.background }]}>LOG YOUR FIRST FOOD</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", paddingHorizontal: 28 },
  eyebrow: { fontSize: 13, fontWeight: "700", letterSpacing: 2 },
  title: { fontSize: 38, fontWeight: "800", letterSpacing: -1.2, lineHeight: 43, marginTop: 16 },
  body: { fontSize: 16, lineHeight: 24, marginTop: 14 },
  button: {
    alignItems: "center",
    borderRadius: 12,
    justifyContent: "center",
    marginTop: 40,
    minHeight: 58,
  },
  buttonLabel: { fontSize: 14, fontWeight: "900", letterSpacing: 1.5 },
  note: { fontSize: 13, lineHeight: 20, marginTop: 14, textAlign: "center" },
});
