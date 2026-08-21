/**
 * Today, as a shell.
 *
 * Deliberately thin. Doc 26 sends a new user from sign-in straight into first
 * capture, but capture is E4 and the ring, the tiles and the entry list are all
 * doc 12's, so E2 lands them somewhere honest instead of somewhere fake. No
 * progress rings here, no zeroed macro tiles pretending to be data.
 *
 * What it does prove is the thing E2 is for: the session survived, and the
 * server knows who this is. The name on screen came back from `/api/users/me/`
 * with a token read out of the Keychain.
 */

import { Link } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function TodayScreen() {
  const session = useSession();
  const palette = usePalette();

  // The layout above this one redirects when signed out, so by the time this
  // renders there is a user. Narrowing rather than asserting keeps that true if
  // the guard ever moves.
  if (session.status !== "signedIn") {
    return null;
  }

  const { user } = session;
  const greeting = user.name || user.email || "you";

  return (
    <View style={[styles.container, { backgroundColor: palette.background }]}>
      <View style={styles.header}>
        <View>
          <Text style={[styles.title, { color: palette.text }]}>Today</Text>
          <Text style={[styles.identity, { color: palette.secondaryText }]}>
            Signed in as {greeting}
          </Text>
        </View>
        <Link href="/settings" style={[styles.settingsLink, { color: palette.accent }]}>
          Settings
        </Link>
      </View>

      <View style={styles.empty}>
        <Text style={[styles.emptyTitle, { color: palette.text }]}>Nothing logged yet</Text>
        <Text style={[styles.emptyBody, { color: palette.secondaryText }]}>
          Photographing a meal and getting the numbers back arrives in E4. Until then this screen is
          here to prove the session holds.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: 24, paddingTop: 72 },
  header: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  title: { fontSize: 32, fontWeight: "700", letterSpacing: -0.5 },
  identity: { fontSize: 14, marginTop: 4 },
  settingsLink: { fontSize: 16, paddingTop: 8 },
  empty: { flex: 1, gap: 10, justifyContent: "center", paddingBottom: 80 },
  emptyTitle: { fontSize: 20, fontWeight: "600", textAlign: "center" },
  emptyBody: { fontSize: 15, lineHeight: 22, textAlign: "center" },
});
