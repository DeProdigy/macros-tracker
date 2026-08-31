/**
 * The third outcome of the launch gate, standing in for the six questions.
 *
 * **Onboarding is a hard gate.** Ruled 30 Aug 2026, reversing the 20 Aug
 * sequencing. The questions come first, the first meal comes after, and there
 * is no skip. So this screen has no way into the app, which is the correct
 * shape and an uncomfortable one while the questions do not exist.
 *
 * It had a *Not now* button until MAC-47. That button wrote nothing and lasted
 * one launch, and the fix for it was briefly a whole `onboarding_skipped_at`
 * column before the sequencing decision removed the reason for either.
 *
 * MAC-50 makes this screen completable by hand. MAC-42 replaces it with the six
 * questions. Until MAC-50 lands, a new user has no route into the app, which is
 * a real cost of the reversal and is written down rather than worked around.
 *
 * **The sign-out below is not a leftover exit.** See its own comment: the gate
 * keeps people out of Today, and it must not keep them out of their own account.
 */

import { Redirect } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function OnboardingPlaceholder() {
  const session = useSession();
  const palette = usePalette();
  const [signingOut, setSigningOut] = useState(false);

  if (session.status === "loading") {
    return null;
  }

  // Outside the (app) group, so this route carries its own guard.
  if (session.status === "signedOut") {
    return <Redirect href="/login" />;
  }

  const handleSignOut = async () => {
    setSigningOut(true);
    // Never rejects, same as Settings: sign-out drops the tokens whether or not
    // the server heard about it, so there is no failure state to render.
    await session.signOut();
  };

  return (
    <View style={[styles.container, { backgroundColor: palette.background }]}>
      <Text style={[styles.title, { color: palette.text }]}>Set your targets</Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        Six questions turn into a calorie and macro target. That flow is E3 and is not built yet.
      </Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        Targets come first. Nothing logs until they exist, so there is no way past this screen yet.
      </Text>

      {/* The gate keeps a user out of Today. It must not keep them out of their
          own account.

          Sign-out and account deletion live in `(app)/settings.tsx`, and
          `(app)/_layout.tsx` now redirects anyone without targets away from that
          whole group. So closing the deep-link hole locked every un-onboarded
          user inside their own session: no sign-out, no switching Apple ID, and
          no way to delete an account they created a minute ago. Deleting the app
          was the only exit.

          That last one has a legal edge. App Review looks for an in-app path to
          account deletion, and in slice 1 every user is un-onboarded, so the
          path existed for nobody.

          Worth naming the shape, because it will recur: **a guard that hides a
          route group hides everything in it, including the screens that are not
          about the feature being guarded.** Ask what else lives behind the
          redirect before adding one. */}
      <Pressable
        accessibilityRole="button"
        disabled={signingOut}
        onPress={() => {
          void handleSignOut();
        }}
        style={[styles.button, { borderColor: palette.hairline }]}
      >
        <Text style={[styles.buttonLabel, { color: palette.secondaryText }]}>
          {signingOut ? "Signing out…" : "Sign out"}
        </Text>
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
