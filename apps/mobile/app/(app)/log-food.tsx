import { createEntry, getGetDayQueryKey } from "@macros/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { LocalDayUnavailable, localDayContext } from "@/lib/local-day";
import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

const validNumber = (value: string) => /^\d+(?:\.\d{1,2})?$/.test(value);

export default function LogFoodScreen() {
  const palette = usePalette();
  const session = useSession();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [calories, setCalories] = useState("");
  const [protein, setProtein] = useState("");
  const [fiber, setFiber] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (session.status !== "signedIn") return null;

  const save = async () => {
    const macros = [calories, protein, fiber].map((value) => (value.trim() === "" ? "0" : value));
    if (
      !name.trim() ||
      !validNumber(quantity) ||
      Number(quantity) <= 0 ||
      macros.some((value) => !validNumber(value)) ||
      !macros.some((value) => Number(value) > 0)
    ) {
      setError("Enter a name, a positive quantity, and at least one macro value.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const context = localDayContext(session.timezoneStatus, session.user.timezone);
      const response = await createEntry({
        ...context,
        eaten_at: new Date().toISOString(),
        item: {
          name: name.trim(),
          quantity,
          calories: macros[0],
          protein_g: macros[1],
          fiber_g: macros[2],
        },
      });
      if (response.status !== 201) throw new Error("Save failed");
      await queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(context.local_date) });
      router.replace("/today");
    } catch (caught) {
      setError(
        caught instanceof LocalDayUnavailable
          ? "Sync your timezone and try again."
          : "Could not save this food. Try again.",
      );
    } finally {
      setSaving(false);
    }
  };

  const input = [styles.input, { borderColor: palette.hairline, color: palette.text }];
  return (
    <ScrollView
      style={{ backgroundColor: palette.background }}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Pressable accessibilityRole="button" onPress={() => router.back()}>
        <Text style={{ color: palette.accent }}>CANCEL</Text>
      </Pressable>
      <Text style={[styles.eyebrow, { color: palette.accent }]}>LOG FOOD</Text>
      <Text style={[styles.title, { color: palette.text }]}>Manual entry</Text>
      <View style={styles.choices}>
        <Pressable accessibilityRole="button" onPress={() => router.push("/photo")}>
          <Text style={{ color: palette.accent }}>PHOTO</Text>
        </Pressable>
        <Text style={{ color: palette.dimText }}>RECENTS</Text>
        <Text style={{ color: palette.accent }}>MANUAL</Text>
      </View>
      <Text style={[styles.label, { color: palette.secondaryText }]}>FOOD NAME</Text>
      <TextInput
        accessibilityLabel="Food name"
        value={name}
        onChangeText={setName}
        placeholder="Greek yogurt"
        placeholderTextColor={palette.dimText}
        style={input}
      />
      <View style={styles.row}>
        <Field label="QUANTITY" value={quantity} onChange={setQuantity} style={input} />
        <Field label="CALORIES" value={calories} onChange={setCalories} style={input} />
      </View>
      <View style={styles.row}>
        <Field label="PROTEIN (G)" value={protein} onChange={setProtein} style={input} />
        <Field label="FIBER (G)" value={fiber} onChange={setFiber} style={input} />
      </View>
      {error ? (
        <Text accessibilityRole="alert" style={[styles.error, { color: palette.error }]}>
          {error}
        </Text>
      ) : null}
      <Pressable
        accessibilityRole="button"
        disabled={saving}
        onPress={() => void save()}
        style={[styles.save, { backgroundColor: palette.accent }]}
      >
        <Text style={styles.saveText}>{saving ? "SAVING" : "SAVE FOOD"}</Text>
      </Pressable>
      <Text style={[styles.note, { color: palette.dimText }]}>
        Recents arrive in a follow-up slice.
      </Text>
    </ScrollView>
  );
}

function Field({
  label,
  value,
  onChange,
  style,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  style: object;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        keyboardType="decimal-pad"
        value={value}
        onChangeText={onChange}
        style={style}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: 48, paddingHorizontal: 24, paddingTop: 64 },
  eyebrow: { fontSize: 12, fontWeight: "800", letterSpacing: 2, marginTop: 30 },
  title: { fontSize: 38, fontWeight: "900", marginTop: 8 },
  choices: { flexDirection: "row", gap: 28, marginVertical: 28 },
  label: { fontSize: 11, fontWeight: "800", letterSpacing: 1.5, marginBottom: 8 },
  input: { borderRadius: 10, borderWidth: 1, fontSize: 18, minHeight: 52, paddingHorizontal: 14 },
  row: { flexDirection: "row", gap: 12, marginTop: 20 },
  field: { flex: 1 },
  fieldLabel: {
    color: "#8b8b8b",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1,
    marginBottom: 8,
  },
  error: { fontSize: 14, lineHeight: 20, marginTop: 18 },
  save: {
    alignItems: "center",
    borderRadius: 12,
    justifyContent: "center",
    marginTop: 28,
    minHeight: 58,
  },
  saveText: { color: "#001018", fontWeight: "900", letterSpacing: 1.2 },
  note: { fontSize: 12, marginTop: 14, textAlign: "center" },
});
