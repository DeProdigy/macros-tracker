import { Pressable, StyleSheet, TextInput, View } from "react-native";

import { Caption, Label } from "@/components/ui/text";
import type { EditableFoodItem } from "@/lib/entry-items";
import { colors, radius, space, tapTarget, type } from "@/lib/theme";

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
  const change = (field: keyof EditableFoodItem, next: string) =>
    onChange({ ...value, [field]: next });

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Label>{label.toUpperCase()}</Label>
        {onRemove ? (
          <Pressable
            accessibilityRole="button"
            disabled={removeDisabled || working}
            onPress={onRemove}
            style={styles.remove}
          >
            <Caption color={removeDisabled ? colors.textDim : colors.error}>REMOVE</Caption>
          </Pressable>
        ) : null}
      </View>
      <Label style={styles.label}>FOOD NAME</Label>
      <TextInput
        accessibilityLabel={`${label} food name`}
        onChangeText={(next) => change("name", next)}
        placeholder="Greek yogurt"
        placeholderTextColor={colors.textDim}
        style={styles.input}
        value={value.name}
      />
      <Label style={styles.label}>PORTION</Label>
      <TextInput
        accessibilityLabel={`${label} portion`}
        onChangeText={(next) => change("portion_label", next)}
        placeholder="1 cup"
        placeholderTextColor={colors.textDim}
        style={styles.input}
        value={value.portion_label}
      />
      <View style={styles.row}>
        <NumberField
          label={`${label} quantity`}
          title="QUANTITY"
          value={value.quantity}
          onChange={(next) => change("quantity", next)}
        />
        <NumberField
          label={`${label} calories`}
          title="CALORIES"
          value={value.calories}
          onChange={(next) => change("calories", next)}
        />
      </View>
      <View style={styles.row}>
        <NumberField
          label={`${label} protein`}
          title="PROTEIN (G)"
          value={value.protein_g}
          onChange={(next) => change("protein_g", next)}
        />
        <NumberField
          label={`${label} fiber`}
          title="FIBER (G)"
          value={value.fiber_g}
          onChange={(next) => change("fiber_g", next)}
        />
      </View>
      {actionLabel && onAction ? (
        <Pressable
          accessibilityRole="button"
          disabled={working}
          onPress={onAction}
          style={styles.action}
        >
          <Caption color={colors.accent}>{working ? "SAVING" : actionLabel}</Caption>
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
}: {
  label: string;
  title: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.field}>
      <Label style={styles.numberLabel}>{title}</Label>
      <TextInput
        accessibilityLabel={label}
        returnKeyType="done"
        keyboardType="decimal-pad"
        onChangeText={onChange}
        style={styles.input}
        value={value}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  action: {
    alignItems: "center",
    borderColor: colors.accent,
    borderRadius: radius.sm,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: space.xl,
    minHeight: tapTarget,
  },
  card: { borderColor: colors.border, borderTopWidth: 1, paddingVertical: space.xl },
  field: { flex: 1 },
  header: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  input: {
    ...type.body,
    borderColor: colors.border,
    borderRadius: radius.sm,
    borderWidth: 1,
    color: colors.text,
    minHeight: 50,
    paddingHorizontal: space.md,
  },
  label: { marginBottom: space.sm, marginTop: space.lg },
  numberLabel: { marginBottom: space.sm },
  remove: { justifyContent: "center", minHeight: tapTarget },
  row: { flexDirection: "row", gap: space.md, marginTop: space.lg },
});
