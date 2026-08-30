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
 * insists on. MAC-42 deletes it in slice 2, and MAC-46 brings the designed
 * bridge screen.
 *
 * *Not now* writes `onboarding_skipped_at` before it routes, which is more than
 * a placeholder usually earns. In slice 1 this button is the only way a new
 * user reaches Today, and therefore the only way they reach the Settings row
 * where targets can be set at all. Without the write the skip lasts exactly one
 * launch and the user has to find this button again on every cold start.
 */

import { updateCurrentUser } from "@macros/api-client";
import { Redirect, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function OnboardingPlaceholder() {
  const session = useSession();
  const palette = usePalette();
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);

  if (session.status === "loading") {
    return null;
  }

  // Outside the (app) group, so this route carries its own guard.
  if (session.status === "signedOut") {
    return <Redirect href="/login" />;
  }

  const skip = async () => {
    setLeaving(true);

    try {
      const response = await updateCurrentUser({
        onboarding_skipped_at: new Date().toISOString(),
      });

      // Narrowed on the status, because the generated type is a union across
      // 200, 400 and 401 and only the 200 carries a user. Same shape as the
      // sign-in call.
      if (response.status === 200) {
        // The gate reads the session, not the network. Without this the
        // redirect below lands on Today and the next cold start reads a stale
        // user and sends them back here.
        session.updateUser(response.data);
      }
    } catch {
      // Deliberately swallowed, and this is the interesting line on the screen.
      //
      // The exit is a promise doc 26 makes. Blocking it on a network call makes
      // it worse than the version that never wrote anything at all: a user with
      // no signal would be trapped on a screen whose whole point is that you
      // can leave it.
      //
      // The cost of failing is that the skip lasts one launch, which is exactly
      // where this screen was before MAC-47. No error message, because there is
      // no action to offer: tapping again is what a returning user does anyway.
    }

    router.replace("/today");
  };

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
        disabled={leaving}
        onPress={() => {
          void skip();
        }}
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
