import { useGetDay, type FoodItem } from "@macros/api-client";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ItemEditor } from "@/components/item-editor";
import {
  emptyEditableItem,
  type EditableFoodItem,
  foodItemToEditable,
  isValidEditableItem,
  useEntryItemMutations,
} from "@/lib/entry-items";
import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function EntryEditorScreen() {
  const palette = usePalette();
  const session = useSession();
  const params = useLocalSearchParams<{ id: string; date: string }>();
  const entryId = Number(params.id);
  const localDate = params.date ?? "";
  const dayQuery = useGetDay(localDate, {
    query: {
      enabled:
        session.status === "signedIn" &&
        session.timezoneStatus === "ready" &&
        Number.isInteger(entryId) &&
        Boolean(localDate),
    },
  });
  const mutations = useEntryItemMutations(localDate, entryId);
  const [adding, setAdding] = useState<EditableFoodItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (session.status !== "signedIn") return null;
  const day = dayQuery.data?.status === 200 ? dayQuery.data.data : null;
  const entry = day?.entries.find((candidate) => candidate.id === entryId);

  const addItem = async () => {
    if (!adding || !isValidEditableItem(adding)) {
      setError("Enter a name, positive quantity, and at least one macro value.");
      return;
    }
    setError(null);
    try {
      await mutations.create.mutateAsync(adding);
      setAdding(null);
    } catch {
      setError("Could not add this item. Try again.");
    }
  };

  return (
    <ScrollView
      style={{ backgroundColor: palette.background }}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Pressable accessibilityRole="button" onPress={() => router.back()}>
        <Text style={{ color: palette.accent }}>BACK TO TODAY</Text>
      </Pressable>
      <Text style={[styles.eyebrow, { color: palette.accent }]}>ENTRY</Text>
      <Text style={[styles.title, { color: palette.text }]}>
        {entry?.description ?? "Edit food"}
      </Text>
      {dayQuery.isLoading ? (
        <Text style={{ color: palette.secondaryText }}>Loading entry...</Text>
      ) : null}
      {dayQuery.isError || (!dayQuery.isLoading && !entry) ? (
        <Text accessibilityRole="alert" style={{ color: palette.error }}>
          Could not load this entry. Return to Today and try again.
        </Text>
      ) : null}
      {entry ? (
        <>
          <View style={styles.totals}>
            <Metric label="CALORIES" value={entry.calories} />
            <Metric label="PROTEIN" value={`${entry.protein_g}g`} />
            <Metric label="FIBER" value={`${entry.fiber_g}g`} />
          </View>
          {entry.items.map((item, index) => (
            <SavedItemEditor
              key={item.id}
              item={item}
              index={index}
              itemCount={entry.items.length}
              working={mutations.update.isPending || mutations.remove.isPending}
              onSave={async (value) => {
                setError(null);
                try {
                  await mutations.update.mutateAsync({ item: value, original: item });
                } catch {
                  setError("Could not save this correction. Your previous values were restored.");
                  throw new Error("Could not save item correction.");
                }
              }}
              onRemove={async () => {
                setError(null);
                try {
                  await mutations.remove.mutateAsync(item.id);
                } catch {
                  setError("Could not remove this item. Your previous values were restored.");
                }
              }}
            />
          ))}
          {adding ? (
            <ItemEditor
              label="New item"
              value={adding}
              onChange={setAdding}
              onRemove={() => setAdding(null)}
              actionLabel="ADD ITEM"
              onAction={() => void addItem()}
              working={mutations.create.isPending}
            />
          ) : (
            <Pressable
              accessibilityRole="button"
              onPress={() => setAdding(emptyEditableItem(`new-${Date.now()}`))}
              style={[styles.add, { borderColor: palette.accent }]}
            >
              <Text style={{ color: palette.accent, fontWeight: "800" }}>ADD MISSED ITEM</Text>
            </Pressable>
          )}
          {entry.items.length === 1 ? (
            <Text style={[styles.note, { color: palette.dimText }]}>
              Delete the entry to remove its last item.
            </Text>
          ) : null}
        </>
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={[styles.error, { color: palette.error }]}>
          {error}
        </Text>
      ) : null}
    </ScrollView>
  );
}

function SavedItemEditor({
  item,
  index,
  itemCount,
  working,
  onSave,
  onRemove,
}: {
  item: FoodItem;
  index: number;
  itemCount: number;
  working: boolean;
  onSave: (item: EditableFoodItem) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [value, setValue] = useState(() => foodItemToEditable(item));
  const [dirty, setDirty] = useState(false);
  const [validationError, setValidationError] = useState(false);
  const serverValueKey = JSON.stringify(foodItemToEditable(item));
  const lastSyncedServerValueKey = useRef(serverValueKey);
  useEffect(() => {
    if (!dirty && serverValueKey !== lastSyncedServerValueKey.current) {
      setValue(foodItemToEditable(item));
      lastSyncedServerValueKey.current = serverValueKey;
    }
  }, [dirty, item, serverValueKey]);

  const save = async () => {
    if (!isValidEditableItem(value)) {
      setValidationError(true);
      return;
    }
    setValidationError(false);
    try {
      await onSave(value);
      setDirty(false);
    } catch {
      setValue(foodItemToEditable(item));
      setDirty(false);
    }
  };

  return (
    <View>
      <ItemEditor
        label={`Item ${index + 1}`}
        value={value}
        onChange={(nextValue) => {
          setValue(nextValue);
          setDirty(true);
        }}
        onRemove={() => void onRemove()}
        removeDisabled={itemCount === 1}
        actionLabel="SAVE CHANGES"
        onAction={() => void save()}
        working={working}
      />
      {validationError ? (
        <Text accessibilityRole="alert" style={styles.validationError}>
          Enter a name, positive quantity, and at least one macro value.
        </Text>
      ) : null}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  add: {
    alignItems: "center",
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 20,
    minHeight: 50,
  },
  content: { paddingBottom: 48, paddingHorizontal: 24, paddingTop: 64 },
  error: { fontSize: 14, lineHeight: 20, marginTop: 20 },
  eyebrow: { fontSize: 12, fontWeight: "800", letterSpacing: 2, marginTop: 30 },
  metric: { backgroundColor: "#17191b", borderRadius: 10, flex: 1, padding: 12 },
  metricLabel: { color: "#8b8f94", fontSize: 10, fontWeight: "800", marginTop: 4 },
  metricValue: { color: "#f5f7f8", fontSize: 22, fontWeight: "900" },
  note: { fontSize: 12, marginTop: 14, textAlign: "center" },
  title: { fontSize: 36, fontWeight: "900", marginBottom: 24, marginTop: 8 },
  totals: { flexDirection: "row", gap: 8, marginBottom: 24 },
  validationError: { color: "#ff6b5b", fontSize: 13, marginBottom: 12 },
});
