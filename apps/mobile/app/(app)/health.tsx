/**
 * The API health check, on device.
 *
 * This was the app's home screen through MAC-20, where it existed to prove the
 * walking skeleton: a device build pointed at Railway that could reach Django
 * and get a real query answered. MAC-31 gave the root route to the launch gate,
 * so it moved here and hangs off Settings.
 *
 * Kept rather than deleted because the check it performs is still the fastest
 * way to tell "the app is broken" from "the API is down", and that question
 * comes up on every device build.
 */

import { ApiError, useHealth, type Health } from "@macros/api-client";
import { useRouter } from "expo-router";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { Screen } from "@/components/ui/screen";
import { Body, Caption, ErrorText, Heading, Label, Muted, Title } from "@/components/ui/text";
import { colors, radius, space, tapTarget } from "@/lib/theme";

/**
 * Reads the unhealthy body out of a failed request.
 *
 * `/api/health/` answers 503 with a full `Health` body when a dependency check
 * fails, so the interesting case arrives as a thrown ApiError rather than as
 * `data`. Rendering "unreachable" for it would throw away the one thing it is
 * trying to say: which dependency is down.
 */
const unhealthyBody = (error: unknown): Health | null => {
  if (!(error instanceof ApiError) || error.status !== 503) {
    return null;
  }

  const body = error.body;
  return typeof body === "object" && body !== null && "database" in body ? (body as Health) : null;
};

export default function HealthScreen() {
  const router = useRouter();

  // `useHealth` is generated from the Django schema — not hand-written. Renaming
  // a field on the API's HealthSerializer makes the `health.` access below fail
  // to typecheck, which is the entire point of the contract pipeline.
  //
  // Health rather than ping on purpose: ping proves the process is up, health
  // proves it can serve a request, because it runs a real query. On a device
  // build pointed at Railway, that difference is the whole walking skeleton.
  const { data, error, isPending } = useHealth();
  // Orval's fetch client resolves to the full response envelope.
  const health = data?.data ?? unhealthyBody(error);

  return (
    <Screen contentStyle={styles.page}>
      <Title>Health check</Title>
      <Muted style={styles.subtitle}>Reads /api/health/, which runs a real query.</Muted>

      <View style={styles.card}>
        <Label>API HEALTH</Label>
        {isPending ? (
          <ActivityIndicator color={colors.accent} />
        ) : !health ? (
          <ErrorText>unreachable</ErrorText>
        ) : (
          <>
            <Heading color={health.status === "ok" ? colors.positive : colors.error}>
              {health.status}
            </Heading>
            <Caption>database {health.database ? "reachable" : "unreachable"}</Caption>
            <Caption>v{health.version}</Caption>
            <Caption>{health.timestamp}</Caption>
          </>
        )}
      </View>

      <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.link}>
        <Body color={colors.accent}>Back to Settings</Body>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    gap: space.xs,
    marginTop: space.sm,
    minWidth: 200,
    padding: space.lg,
  },
  link: { justifyContent: "center", marginTop: space.sm, minHeight: tapTarget },
  page: {
    alignItems: "center",
    gap: space.md,
    justifyContent: "center",
    padding: space.xl,
  },
  subtitle: { textAlign: "center" },
});
