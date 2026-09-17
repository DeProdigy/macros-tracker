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
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Body, ErrorText, Label, Muted, Numeral, Title } from "@/components/ui/text";

import { colors, radius, space, tapTarget, type } from "@/lib/theme";
import { useSession } from "@/lib/session";

type Busy = "none" | "signingOut" | "deleting";

export default function SettingsScreen() {
  const session = useSession();
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
    <Screen contentStyle={styles.content} scroll>
      <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.back}>
        <Body color={colors.accent}>‹ Today</Body>
      </Pressable>

      <Title>Settings</Title>

      <View style={styles.group}>
        <Label color={colors.textDim}>ACCOUNT</Label>
        <Body style={styles.value}>{user.name || "No name"}</Body>
        <Muted style={styles.meta}>
          {/* Apple may withhold the address or hand back a private relay one, so
              this is genuinely allowed to be empty. */}
          {user.email ?? "Apple is hiding your email address"}
        </Muted>
        <Muted style={styles.meta}>Signed in with Apple</Muted>
      </View>

      <View style={styles.group}>
        <Label color={colors.textDim}>TARGETS</Label>
        {targetsLoading ? (
          <View accessibilityLabel="Loading current targets" style={styles.targetStatus}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : targetsFailure ? (
          <View style={styles.targetStatus}>
            <Muted style={styles.meta}>Current targets did not load.</Muted>
            <Pressable
              accessibilityRole="button"
              onPress={() => void loadTargets()}
              style={styles.link}
            >
              <Body color={colors.accent}>Try again</Body>
            </Pressable>
          </View>
        ) : target ? (
          <View style={styles.targetMetrics}>
            <TargetMetric label="KCAL" value={target.calories} color={colors.accent} />
            <TargetMetric label="PROTEIN" value={target.protein_g} color={colors.positive} />
            <TargetMetric label="FIBER" value={target.fiber_g} color={colors.protein} />
          </View>
        ) : (
          <Muted style={styles.meta}>No targets set.</Muted>
        )}

        <View style={styles.targetActions}>
          <Link href="/targets" style={styles.targetAction}>
            Adjust
          </Link>
          <Link href="/target-history" style={styles.targetAction}>
            History
          </Link>
        </View>
      </View>

      <View style={styles.group}>
        <Label color={colors.textDim}>DIAGNOSTICS</Label>
        <Link href="/health" style={styles.linkText}>
          API health
        </Link>
      </View>

      {failure ? <ErrorText>{failure}</ErrorText> : null}

      <Button
        busy={busy === "signingOut"}
        disabled={busy !== "none"}
        onPress={handleSignOut}
        title="Sign out"
        variant="secondary"
      />

      <View style={[styles.group, styles.dangerGroup]}>
        <Label color={colors.error}>DANGER</Label>

        {confirmingDelete ? (
          <>
            {/*
              A timeline replaces a generic warning because the 30-day recovery
              window changes the decision. If deletion becomes immediate, this
              sequence must change with the server behavior.
            */}
            <Body style={styles.value}>Delete your account?</Body>
            <Muted style={styles.meta}>
              Now: signed out everywhere, and you can no longer log in.
            </Muted>
            <Muted style={styles.meta}>
              For 30 days: your entries and photos are held, and nothing is visible to you.
            </Muted>
            <Muted style={styles.meta}>After that: purged for good, rows and photos alike.</Muted>
            <Muted style={styles.meta}>
              Signing in with the same Apple ID during those 30 days brings the account back.
            </Muted>

            <Button
              busy={busy === "deleting"}
              disabled={busy !== "none"}
              onPress={handleDelete}
              style={styles.dangerButton}
              title="Delete my account"
              variant="destructive"
            />

            <Button
              disabled={busy !== "none"}
              onPress={() => setConfirmingDelete(false)}
              style={styles.dangerButton}
              title="Keep my account"
              variant="secondary"
            />
          </>
        ) : (
          <Button
            disabled={busy !== "none"}
            onPress={() => setConfirmingDelete(true)}
            style={styles.dangerButton}
            title="Delete my account"
            variant="destructive"
          />
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: { justifyContent: "center", minHeight: tapTarget },
  content: {
    gap: space.xl,
    paddingBottom: space.empty,
    paddingHorizontal: space.xl,
    paddingTop: space.lg,
  },
  dangerButton: { marginTop: space.sm },
  dangerGroup: { borderColor: colors.error },
  group: {
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    gap: space.xs,
    padding: space.lg,
  },
  link: { justifyContent: "center", minHeight: tapTarget },
  linkText: {
    color: colors.accent,
    fontFamily: type.body.fontFamily,
    fontSize: type.body.fontSize,
    paddingVertical: space.md,
  },
  meta: { fontSize: type.caption.fontSize, lineHeight: 20 },
  targetAction: {
    borderColor: colors.border,
    borderRadius: radius.sm,
    borderWidth: 1,
    color: colors.accent,
    flex: 1,
    fontFamily: type.label.fontFamily,
    fontSize: type.label.fontSize,
    letterSpacing: type.label.letterSpacing,
    overflow: "hidden",
    paddingVertical: space.lg,
    textAlign: "center",
    textTransform: "uppercase",
  },
  targetActions: { flexDirection: "row", gap: space.sm, marginTop: space.sm },
  targetMetric: { gap: 2 },
  targetMetrics: { flexDirection: "row", gap: space.lg, paddingVertical: space.sm },
  targetStatus: { gap: space.sm, justifyContent: "center", minHeight: tapTarget },
  targetValue: { fontSize: type.heading.fontSize },
  value: { fontFamily: type.heading.fontFamily },
});

const TargetMetric = ({ label, value, color }: { label: string; value: number; color: string }) => (
  <View style={styles.targetMetric}>
    <Numeral color={color} style={styles.targetValue}>
      {value.toLocaleString()}
    </Numeral>
    <Label color={colors.textDim}>{label}</Label>
  </View>
);
