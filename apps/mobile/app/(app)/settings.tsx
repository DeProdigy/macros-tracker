/**
 * Settings owns reads, while the target editor owns writes.
 *
 * Keeping the current-target request here lets this screen refresh on focus.
 * Passing saved values through route parameters would couple two routes. It
 * would also miss changes from deep links or a future second editor.
 */

import { ApiError, getCurrentTarget, type TargetVersion } from "@macros/api-client";
import { Link, useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

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
  const [target, setTarget] = useState<TargetVersion | null>(null);
  const [targetsLoading, setTargetsLoading] = useState(true);
  const [targetsFailure, setTargetsFailure] = useState(false);
  const mounted = useRef(true);

  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  const loadTargets = useCallback(async (isActive: () => boolean = () => true) => {
    setTargetsLoading(true);
    setTargetsFailure(false);

    try {
      const response = await getCurrentTarget();
      if (!mounted.current || !isActive()) return;
      if (response.status !== 200) {
        throw new Error(`Unexpected current target status: ${response.status}`);
      }
      setTarget(response.data);
    } catch (error) {
      if (!mounted.current || !isActive()) return;
      if (error instanceof ApiError && error.status === 404) {
        setTarget(null);
      } else {
        setTargetsFailure(true);
      }
    } finally {
      if (mounted.current && isActive()) setTargetsLoading(false);
    }
  }, []);

  // The editor is a separate route. A focus read makes the version saved there
  // visible when Settings returns, without coupling the two screens through
  // route parameters or shared draft state.
  useFocusEffect(
    useCallback(() => {
      let active = true;
      if (session.status === "signedIn") void loadTargets(() => active);
      return () => {
        active = false;
      };
    }, [loadTargets, session.status]),
  );

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
        <Text style={[styles.groupLabel, { color: palette.dimText }]}>Targets</Text>
        {targetsLoading ? (
          <View accessibilityLabel="Loading current targets" style={styles.targetStatus}>
            <ActivityIndicator color={palette.accent} />
          </View>
        ) : targetsFailure ? (
          <View style={styles.targetStatus}>
            <Text style={[styles.meta, { color: palette.secondaryText }]}>
              Current targets did not load.
            </Text>
            <Pressable accessibilityRole="button" onPress={() => void loadTargets()}>
              <Text style={[styles.link, { color: palette.accent }]}>Try again</Text>
            </Pressable>
          </View>
        ) : target ? (
          <View style={styles.targetMetrics}>
            <TargetMetric label="KCAL" value={target.calories} color={palette.accent} />
            <TargetMetric label="PROTEIN" value={target.protein_g} color="#70e6a3" />
            <TargetMetric label="FIBER" value={target.fiber_g} color="#ad8cff" />
          </View>
        ) : (
          <Text style={[styles.meta, { color: palette.secondaryText }]}>No targets set.</Text>
        )}

        <View style={styles.targetActions}>
          <Link
            href="/targets"
            style={[styles.targetAction, { color: palette.accent, borderColor: palette.hairline }]}
          >
            Adjust
          </Link>
          <Link
            href="/target-history"
            style={[styles.targetAction, { color: palette.accent, borderColor: palette.hairline }]}
          >
            History
          </Link>
        </View>
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
            {/*
              A timeline replaces a generic warning because the 30-day recovery
              window changes the decision. If deletion becomes immediate, this
              sequence must change with the server behavior.
            */}
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
  targetStatus: { gap: 8, minHeight: 48, justifyContent: "center" },
  targetMetrics: { flexDirection: "row", gap: 18, paddingVertical: 10 },
  targetMetric: { gap: 2 },
  targetValue: { fontSize: 24, fontWeight: "800" },
  targetUnit: { color: "#6b6b6b", fontSize: 10, letterSpacing: 0.8 },
  targetActions: { flexDirection: "row", gap: 10, marginTop: 8 },
  targetAction: {
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    flex: 1,
    fontSize: 14,
    fontWeight: "700",
    overflow: "hidden",
    paddingVertical: 13,
    textAlign: "center",
    textTransform: "uppercase",
  },
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

const TargetMetric = ({ label, value, color }: { label: string; value: number; color: string }) => (
  <View style={styles.targetMetric}>
    <Text style={[styles.targetValue, { color }]}>{value.toLocaleString()}</Text>
    <Text style={styles.targetUnit}>{label}</Text>
  </View>
);
