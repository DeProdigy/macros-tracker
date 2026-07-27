import { usePing } from "@macros/api-client";
import { Link } from "expo-router";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

export default function HomeScreen() {
  // `usePing` is generated from the Django schema — not hand-written. Renaming
  // a field on the API's PingSerializer makes the `ping.` access below fail to
  // typecheck, which is the entire point of the contract pipeline.
  const { data, isPending, isError } = usePing();
  // Orval's fetch client resolves to the full response envelope.
  const ping = data?.data;

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Macros Tracker</Text>
      <Text style={styles.subtitle}>Mobile scaffold is running.</Text>

      <View style={styles.card}>
        <Text style={styles.cardLabel}>API status</Text>
        {isPending ? (
          <ActivityIndicator />
        ) : isError || !ping ? (
          <Text style={styles.error}>unreachable</Text>
        ) : (
          <>
            <Text style={styles.status}>{ping.status}</Text>
            <Text style={styles.meta}>v{ping.version}</Text>
            <Text style={styles.meta}>{ping.timestamp}</Text>
          </>
        )}
      </View>

      <Link href="/login" style={styles.link}>
        Go to login (placeholder)
      </Link>
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
  status: { fontSize: 20, fontWeight: "600", color: "#1a8a3f" },
  meta: { fontSize: 13, opacity: 0.6 },
  error: { fontSize: 16, color: "#c0392b" },
  link: { fontSize: 16, color: "#208aef", marginTop: 8 },
});
