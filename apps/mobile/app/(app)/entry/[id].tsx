import {
  createEntry,
  deleteEntry,
  getGetDayQueryKey,
  getGetEntryQueryKey,
  getGetFoodsQueryKey,
  useGetEntry,
  type FoodItem,
} from "@macros/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Image, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ItemEditor } from "@/components/item-editor";
import {
  emptyEditableItem,
  type EditableFoodItem,
  foodItemToEditable,
  isValidEditableItem,
  useEntryItemMutations,
} from "@/lib/entry-items";
import { entryTimingForDate, localIsoDate } from "@/lib/local-day";
import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function EntryEditorScreen() {
  const palette = usePalette();
  const session = useSession();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ id: string; date: string }>();
  const entryId = Number(params.id);
  const localDate = params.date ?? "";
  const entryQuery = useGetEntry(entryId, {
    query: {
      enabled: session.status === "signedIn" && Number.isInteger(entryId) && entryId > 0,
    },
  });
  const mutations = useEntryItemMutations(localDate, entryId);
  const [adding, setAdding] = useState<EditableFoodItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteVisible, setDeleteVisible] = useState(false);
  const [working, setWorking] = useState(false);

  if (session.status !== "signedIn") return null;
  const entry = entryQuery.data?.status === 200 ? entryQuery.data.data : null;
  const today = localIsoDate(new Date());

  const returnToDay = (date: string) => router.replace({ pathname: "/today", params: { date } });

  const logAgain = async () => {
    if (!entry) return;
    setWorking(true);
    setError(null);
    try {
      const timing = entryTimingForDate(session.timezoneStatus, session.user.timezone, today);
      const response = await createEntry({ ...timing, source_entry_id: entry.id });
      if (response.status !== 201) throw new Error("Save failed.");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(today) }),
        queryClient.invalidateQueries({ queryKey: getGetFoodsQueryKey(), refetchType: "none" }),
      ]);
      returnToDay(today);
    } catch {
      setError("Could not log this entry again. Try again.");
    } finally {
      setWorking(false);
    }
  };

  const removeEntry = async () => {
    if (!entry) return;
    setWorking(true);
    setError(null);
    try {
      const response = await deleteEntry(entry.id);
      if (response.status !== 204) throw new Error("Delete failed.");
      queryClient.removeQueries({ queryKey: getGetEntryQueryKey(entry.id) });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(localDate) }),
        queryClient.invalidateQueries({ queryKey: getGetFoodsQueryKey(), refetchType: "none" }),
      ]);
      returnToDay(localDate);
    } catch {
      setError("Could not delete this entry. Try again.");
      setDeleteVisible(false);
    } finally {
      setWorking(false);
    }
  };

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
      <Pressable accessibilityRole="button" onPress={() => returnToDay(localDate)}>
        <Text style={{ color: palette.accent }}>
          {localDate === today ? "BACK TO TODAY" : "BACK TO DAY"}
        </Text>
      </Pressable>
      <Text style={[styles.eyebrow, { color: palette.accent }]}>ENTRY</Text>
      <Text style={[styles.title, { color: palette.text }]}>
        {entry?.description ?? "Edit food"}
      </Text>
      {entryQuery.isLoading ? (
        <Text style={{ color: palette.secondaryText }}>Loading entry...</Text>
      ) : null}
      {entryQuery.isError || (!entryQuery.isLoading && !entry) ? (
        <Text accessibilityRole="alert" style={{ color: palette.error }}>
          Could not load this entry. Return to Today and try again.
        </Text>
      ) : null}
      {entry ? (
        <>
          {entry.photo_url ? (
            <Image
              accessibilityLabel={`${entry.description} meal`}
              source={{ uri: entry.photo_url }}
              style={styles.photo}
            />
          ) : null}
          <Text style={[styles.metadata, { color: palette.secondaryText }]}>
            {entry.source.toUpperCase()} ·{" "}
            {new Date(entry.eaten_at).toLocaleTimeString([], {
              hour: "numeric",
              minute: "2-digit",
            })}
          </Text>
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
          <Pressable
            accessibilityRole="button"
            disabled={working}
            onPress={() => void logAgain()}
            style={[styles.primary, { backgroundColor: palette.accent }]}
          >
            <Text style={styles.primaryText}>{working ? "WORKING" : "LOG AGAIN"}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            disabled={working}
            onPress={() => setDeleteVisible(true)}
            style={[styles.delete, { borderColor: palette.error }]}
          >
            <Text style={{ color: palette.error, fontWeight: "800" }}>DELETE ENTRY</Text>
          </Pressable>
        </>
      ) : null}
      {error ? (
        <Text accessibilityRole="alert" style={[styles.error, { color: palette.error }]}>
          {error}
        </Text>
      ) : null}
      <Modal
        animationType="fade"
        onRequestClose={() => setDeleteVisible(false)}
        transparent
        visible={deleteVisible}
      >
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.background }]}>
            <Text style={[styles.modalTitle, { color: palette.text }]}>Delete this entry?</Text>
            <Text style={[styles.modalBody, { color: palette.secondaryText }]}>
              {entry
                ? `This removes ${entry.description} and ${entry.calories} calories from this day.`
                : "This removes the entry from this day."}
            </Text>
            <Pressable
              accessibilityRole="button"
              disabled={working}
              onPress={() => void removeEntry()}
              style={[styles.primary, { backgroundColor: palette.error }]}
            >
              <Text style={styles.deleteText}>{working ? "DELETING" : "DELETE"}</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              disabled={working}
              onPress={() => setDeleteVisible(false)}
              style={styles.cancelDelete}
            >
              <Text style={{ color: palette.accent, fontWeight: "800" }}>CANCEL</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
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
    if (!dirty) return;
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
  cancelDelete: { alignItems: "center", justifyContent: "center", minHeight: 48 },
  delete: {
    alignItems: "center",
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 12,
    minHeight: 52,
  },
  deleteText: { color: "#ffffff", fontWeight: "900", letterSpacing: 1.2 },
  error: { fontSize: 14, lineHeight: 20, marginTop: 20 },
  eyebrow: { fontSize: 12, fontWeight: "800", letterSpacing: 2, marginTop: 30 },
  metadata: { fontSize: 12, fontWeight: "700", letterSpacing: 1, marginBottom: 18 },
  metric: { backgroundColor: "#17191b", borderRadius: 10, flex: 1, padding: 12 },
  metricLabel: { color: "#8b8f94", fontSize: 10, fontWeight: "800", marginTop: 4 },
  metricValue: { color: "#f5f7f8", fontSize: 22, fontWeight: "900" },
  modalBackdrop: {
    alignItems: "center",
    backgroundColor: "rgba(0, 0, 0, 0.6)",
    flex: 1,
    justifyContent: "center",
    padding: 24,
  },
  modalBody: { lineHeight: 21, marginTop: 10 },
  modalCard: { borderRadius: 16, padding: 24, width: "100%" },
  modalTitle: { fontSize: 24, fontWeight: "900" },
  note: { fontSize: 12, marginTop: 14, textAlign: "center" },
  photo: { borderRadius: 14, height: 260, marginBottom: 18, width: "100%" },
  primary: {
    alignItems: "center",
    borderRadius: 12,
    justifyContent: "center",
    marginTop: 24,
    minHeight: 56,
  },
  primaryText: { color: "#001018", fontWeight: "900", letterSpacing: 1.2 },
  title: { fontSize: 36, fontWeight: "900", marginBottom: 24, marginTop: 8 },
  totals: { flexDirection: "row", gap: 8, marginBottom: 24 },
  validationError: { color: "#ff6b5b", fontSize: 13, marginBottom: 12 },
});
