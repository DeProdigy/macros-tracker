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
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

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
    <View style={styles.container}>
      <Text style={styles.title}>Health check</Text>
      <Text style={styles.subtitle}>Reads /api/health/, which runs a real query.</Text>

      <View style={styles.card}>
        <Text style={styles.cardLabel}>API health</Text>
        {isPending ? (
          <ActivityIndicator />
        ) : !health ? (
          <Text style={styles.error}>unreachable</Text>
        ) : (
          <>
            <Text style={[styles.status, health.status === "ok" ? styles.ok : styles.error]}>
              {health.status}
            </Text>
            <Text style={styles.meta}>
              database {health.database ? "reachable" : "unreachable"}
            </Text>
            <Text style={styles.meta}>v{health.version}</Text>
            <Text style={styles.meta}>{health.timestamp}</Text>
          </>
        )}
      </View>

      <Pressable accessibilityRole="button" onPress={() => router.back()}>
        <Text style={styles.link}>Back to Settings</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    padding: 24,
  },
  title: { fontSize: 28, fontWeight: "600" },
  subtitle: { fontSize: 16, opacity: 0.7 },
  card: {
    alignItems: "center",
    gap: 4,
    marginTop: 8,
    padding: 16,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: "#c8c8c8",
    minWidth: 200,
  },
  cardLabel: { fontSize: 12, textTransform: "uppercase", opacity: 0.5 },
  status: { fontSize: 20, fontWeight: "600" },
  ok: { color: "#1a8a3f" },
  meta: { fontSize: 13, opacity: 0.6 },
  error: { fontSize: 16, color: "#c0392b" },
  link: { fontSize: 16, color: "#208aef", marginTop: 8 },
});
