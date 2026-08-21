/**
 * Settings, minimal.
 *
 * Doc 16 owns the real one: six groups, target history, AI usage, the Apple
 * Health toggle. None of that exists yet. Two things are here because they have
 * to be — both stores require an in-app deletion path, which is the whole
 * reason account deletion appears this early in the build, and deletion is
 * untestable without a screen to trigger it from.
 *
 * The delete confirmation is a panel rather than doc 16's typed `DELETE` field.
 * The timeline copy is doc 16's, because that is the part that matters: the
 * screen names what happens and when, instead of asking "are you sure".
 */

import { Link, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

type Busy = "none" | "signingOut" | "deleting";

export default function SettingsScreen() {
  const session = useSession();
  const palette = usePalette();
  const router = useRouter();
  const [busy, setBusy] = useState<Busy>("none");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  if (session.status !== "signedIn") {
    return null;
  }

  const { user, signOut, deleteAccount } = session;

  const handleSignOut = async () => {
    setBusy("signingOut");
    setFailure(null);
    // Never rejects: sign-out drops the tokens whether or not the server heard
    // about it, so there is no failure state to render.
    await signOut();
  };

  const handleDelete = async () => {
    setBusy("deleting");
    setFailure(null);

    try {
      await deleteAccount();
    } catch {
      // The account still exists, so the session stays. Signing someone out of
      // an account that survived would tell them the deletion worked.
      setBusy("none");
      setFailure("Your account wasn't deleted. Nothing changed, so try again in a minute.");
    }
  };

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      style={[styles.container, { backgroundColor: palette.background }]}
    >
      <Pressable onPress={() => router.back()}>
        <Text style={[styles.back, { color: palette.accent }]}>‹ Today</Text>
      </Pressable>

      <Text style={[styles.title, { color: palette.text }]}>Settings</Text>

      <View style={[styles.group, { borderColor: palette.hairline }]}>
        <Text style={[styles.groupLabel, { color: palette.dimText }]}>Account</Text>
        <Text style={[styles.value, { color: palette.text }]}>{user.name || "No name"}</Text>
        <Text style={[styles.meta, { color: palette.secondaryText }]}>
          {/* Apple may withhold the address or hand back a private relay one, so
              this is genuinely allowed to be empty. */}
          {user.email ?? "Apple is hiding your email address"}
        </Text>
        <Text style={[styles.meta, { color: palette.secondaryText }]}>Signed in with Apple</Text>
      </View>

      <View style={[styles.group, { borderColor: palette.hairline }]}>
        <Text style={[styles.groupLabel, { color: palette.dimText }]}>Diagnostics</Text>
        <Link href="/health" style={[styles.link, { color: palette.accent }]}>
          API health
        </Link>
      </View>

      {failure ? <Text style={[styles.failure, { color: palette.error }]}>{failure}</Text> : null}

      <Pressable
        accessibilityRole="button"
        disabled={busy !== "none"}
        onPress={handleSignOut}
        style={[styles.button, { borderColor: palette.hairline }]}
      >
        <Text style={[styles.buttonLabel, { color: palette.text }]}>
          {busy === "signingOut" ? "Signing out…" : "Sign out"}
        </Text>
      </Pressable>

      <View style={[styles.group, { borderColor: palette.error }]}>
        <Text style={[styles.groupLabel, { color: palette.error }]}>Danger</Text>

        {confirmingDelete ? (
          <>
            {/* Doc 16: a timeline, not a warning. The grace period is the
                answer to "have I just destroyed a year of logging", and the
                screen should say so before the tap rather than after. */}
            <Text style={[styles.value, { color: palette.text }]}>Delete your account?</Text>
            <Text style={[styles.meta, { color: palette.secondaryText }]}>
              Now: signed out everywhere, and you can no longer log in.
            </Text>
            <Text style={[styles.meta, { color: palette.secondaryText }]}>
              For 30 days: your entries and photos are held, and nothing is visible to you.
            </Text>
            <Text style={[styles.meta, { color: palette.secondaryText }]}>
              After that: purged for good, rows and photos alike.
            </Text>
            <Text style={[styles.meta, { color: palette.secondaryText }]}>
              Signing in with the same Apple ID during those 30 days brings the account back.
            </Text>

            <Pressable
              accessibilityRole="button"
              disabled={busy !== "none"}
              onPress={handleDelete}
              style={[styles.button, { borderColor: palette.error }]}
            >
              <Text style={[styles.buttonLabel, { color: palette.error }]}>
                {busy === "deleting" ? "Deleting…" : "Delete my account"}
              </Text>
            </Pressable>

            <Pressable
              accessibilityRole="button"
              disabled={busy !== "none"}
              onPress={() => setConfirmingDelete(false)}
              style={[styles.button, { borderColor: palette.hairline }]}
            >
              <Text style={[styles.buttonLabel, { color: palette.text }]}>Keep my account</Text>
            </Pressable>
          </>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={busy !== "none"}
            onPress={() => setConfirmingDelete(true)}
            style={[styles.button, { borderColor: palette.error }]}
          >
            <Text style={[styles.buttonLabel, { color: palette.error }]}>Delete my account</Text>
          </Pressable>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { gap: 20, paddingBottom: 64, paddingHorizontal: 24, paddingTop: 72 },
  back: { fontSize: 16 },
  title: { fontSize: 32, fontWeight: "700", letterSpacing: -0.5 },
  group: { borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, gap: 6, padding: 16 },
  groupLabel: { fontSize: 12, letterSpacing: 0.5, textTransform: "uppercase" },
  value: { fontSize: 17, fontWeight: "600" },
  meta: { fontSize: 14, lineHeight: 20 },
  link: { fontSize: 16 },
  failure: { fontSize: 14, lineHeight: 20 },
  button: {
    alignItems: "center",
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    marginTop: 8,
    paddingVertical: 14,
  },
  buttonLabel: { fontSize: 16, fontWeight: "600" },
});
