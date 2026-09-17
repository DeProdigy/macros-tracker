import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { EditableFoodItem } from "@/lib/entry-items";
import { usePalette } from "@/lib/theme";

type Props = {
  label: string;
  value: EditableFoodItem;
  onChange: (value: EditableFoodItem) => void;
  onRemove?: () => void;
  removeDisabled?: boolean;
  actionLabel?: string;
  onAction?: () => void;
  working?: boolean;
};

export function ItemEditor({
  label,
  value,
  onChange,
  onRemove,
  removeDisabled = false,
  actionLabel,
  onAction,
  working = false,
}: Props) {
  const palette = usePalette();
  const inputStyle = [styles.input, { borderColor: palette.hairline, color: palette.text }];
  const change = (field: keyof EditableFoodItem, next: string) =>
    onChange({ ...value, [field]: next });

  return (
    <View style={[styles.card, { borderColor: palette.hairline }]}>
      <View style={styles.header}>
        <Text style={[styles.itemLabel, { color: palette.secondaryText }]}>
          {label.toUpperCase()}
        </Text>
        {onRemove ? (
          <Pressable
            accessibilityRole="button"
            disabled={removeDisabled || working}
            onPress={onRemove}
          >
            <Text style={{ color: removeDisabled ? palette.dimText : palette.error }}>REMOVE</Text>
          </Pressable>
        ) : null}
      </View>
      <Text style={[styles.label, { color: palette.secondaryText }]}>FOOD NAME</Text>
      <TextInput
        accessibilityLabel={`${label} food name`}
        onChangeText={(next) => change("name", next)}
        placeholder="Greek yogurt"
        placeholderTextColor={palette.dimText}
        style={inputStyle}
        value={value.name}
      />
      <Text style={[styles.label, { color: palette.secondaryText }]}>PORTION</Text>
      <TextInput
        accessibilityLabel={`${label} portion`}
        onChangeText={(next) => change("portion_label", next)}
        placeholder="1 cup"
        placeholderTextColor={palette.dimText}
        style={inputStyle}
        value={value.portion_label}
      />
      <View style={styles.row}>
        <NumberField
          label={`${label} quantity`}
          title="QUANTITY"
          value={value.quantity}
          onChange={(next) => change("quantity", next)}
          style={inputStyle}
        />
        <NumberField
          label={`${label} calories`}
          title="CALORIES"
          value={value.calories}
          onChange={(next) => change("calories", next)}
          style={inputStyle}
        />
      </View>
      <View style={styles.row}>
        <NumberField
          label={`${label} protein`}
          title="PROTEIN (G)"
          value={value.protein_g}
          onChange={(next) => change("protein_g", next)}
          style={inputStyle}
        />
        <NumberField
          label={`${label} fiber`}
          title="FIBER (G)"
          value={value.fiber_g}
          onChange={(next) => change("fiber_g", next)}
          style={inputStyle}
        />
      </View>
      {actionLabel && onAction ? (
        <Pressable
          accessibilityRole="button"
          disabled={working}
          onPress={onAction}
          style={[styles.action, { borderColor: palette.accent }]}
        >
          <Text style={{ color: palette.accent, fontWeight: "800" }}>
            {working ? "SAVING" : actionLabel}
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function NumberField({
  label,
  title,
  value,
  onChange,
  style,
}: {
  label: string;
  title: string;
  value: string;
  onChange: (value: string) => void;
  style: object;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.numberLabel}>{title}</Text>
      <TextInput
        accessibilityLabel={label}
        keyboardType="decimal-pad"
        onChangeText={onChange}
        style={style}
        value={value}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  action: {
    alignItems: "center",
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 20,
    minHeight: 48,
  },
  card: { borderTopWidth: 1, paddingVertical: 20 },
  field: { flex: 1 },
  header: { flexDirection: "row", justifyContent: "space-between" },
  input: {
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 16,
    minHeight: 50,
    paddingHorizontal: 12,
  },
  itemLabel: { fontSize: 11, fontWeight: "800", letterSpacing: 1.4 },
  label: { fontSize: 10, fontWeight: "800", letterSpacing: 1.2, marginBottom: 7, marginTop: 16 },
  numberLabel: {
    color: "#8b8b8b",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
    marginBottom: 7,
  },
  row: { flexDirection: "row", gap: 12, marginTop: 16 },
});
