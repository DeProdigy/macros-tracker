import { Link } from "expo-router";
import { StyleSheet, Text, View } from "react-native";

export default function HomeScreen() {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Macros Tracker</Text>
      <Text style={styles.subtitle}>Mobile scaffold is running.</Text>
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
  link: { fontSize: 16, color: "#208aef", marginTop: 8 },
});
