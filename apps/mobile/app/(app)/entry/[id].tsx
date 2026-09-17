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
import { Image, Modal, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ItemEditor } from "@/components/item-editor";
import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Caption, ErrorText, Heading, Label, Muted, Numeral, Title } from "@/components/ui/text";
import {
  emptyEditableItem,
  type EditableFoodItem,
  foodItemToEditable,
  isValidEditableItem,
  useEntryItemMutations,
} from "@/lib/entry-items";
import { macroValue } from "@/lib/format";
import { entryTimingForDate, localIsoDate, parseLocalIsoDate } from "@/lib/local-day";
import { colors, radius, space, tapTarget, type } from "@/lib/theme";
import { useSession } from "@/lib/session";

export default function EntryEditorScreen() {
  // The delete modal sits outside the Screen wrapper, so it reads the inset
  // itself to keep its card clear of the home indicator.
  const insets = useSafeAreaInsets();
  const session = useSession();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{
    id: string | string[];
    date?: string | string[];
  }>();
  const idValue = Array.isArray(params.id) ? params.id[0] : params.id;
  const requestedDate = Array.isArray(params.date) ? params.date[0] : params.date;
  const today = localIsoDate(new Date());
  const entryId = Number(idValue);
  const localDate =
    requestedDate && parseLocalIsoDate(requestedDate) && requestedDate <= today
      ? requestedDate
      : today;
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
    <Screen contentStyle={styles.content} keyboard scroll>
      <Pressable
        accessibilityRole="button"
        onPress={() => returnToDay(localDate)}
        style={styles.back}
      >
        <Caption color={colors.accent}>
          {localDate === today ? "BACK TO TODAY" : "BACK TO DAY"}
        </Caption>
      </Pressable>
      <Label color={colors.accent} style={styles.eyebrow}>
        ENTRY
      </Label>
      <Title style={styles.title}>{entry?.description ?? "Edit food"}</Title>
      {entryQuery.isLoading ? <Muted>Loading entry...</Muted> : null}
      {entryQuery.isError || (!entryQuery.isLoading && !entry) ? (
        <ErrorText>Could not load this entry. Return to Today and try again.</ErrorText>
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
          <Label style={styles.metadata}>
            {entry.source.toUpperCase()} ·{" "}
            {new Date(entry.eaten_at)
              .toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
              .toUpperCase()}
          </Label>
          <View style={styles.totals}>
            <Metric label="CALORIES" value={macroValue(entry.calories)} />
            <Metric label="PROTEIN" value={`${macroValue(entry.protein_g)}g`} />
            <Metric label="FIBER" value={`${macroValue(entry.fiber_g)}g`} />
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
              style={styles.add}
            >
              <Caption color={colors.accent}>ADD MISSED ITEM</Caption>
            </Pressable>
          )}
          {entry.items.length === 1 ? (
            <Caption color={colors.textDim} style={styles.note}>
              Delete the entry to remove its last item.
            </Caption>
          ) : null}
          <Button
            busy={working}
            disabled={working}
            onPress={() => void logAgain()}
            style={styles.primary}
            title="Log again"
          />
          <Button
            disabled={working}
            onPress={() => setDeleteVisible(true)}
            style={styles.delete}
            title="Delete entry"
            variant="destructive"
          />
        </>
      ) : null}
      {error ? <ErrorText style={styles.error}>{error}</ErrorText> : null}
      <Modal
        animationType="fade"
        onRequestClose={() => setDeleteVisible(false)}
        transparent
        visible={deleteVisible}
      >
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { marginBottom: insets.bottom }]}>
            <Heading>Delete this entry?</Heading>
            <Muted style={styles.modalBody}>
              {entry
                ? `This removes ${entry.description} and ${macroValue(entry.calories)} calories from this day.`
                : "This removes the entry from this day."}
            </Muted>
            <Button
              busy={working}
              disabled={working}
              onPress={() => void removeEntry()}
              style={styles.confirmDelete}
              title="Delete"
              variant="destructive"
            />
            <Pressable
              accessibilityRole="button"
              disabled={working}
              onPress={() => setDeleteVisible(false)}
              style={styles.cancelDelete}
            >
              <Caption color={colors.accent}>CANCEL</Caption>
            </Pressable>
          </View>
        </View>
      </Modal>
    </Screen>
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
        <ErrorText style={styles.validationError}>
          Enter a name, positive quantity, and at least one macro value.
        </ErrorText>
      ) : null}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <View style={styles.metric}>
      <Numeral style={styles.metricValue}>{value}</Numeral>
      <Label style={styles.metricLabel}>{label}</Label>
    </View>
  );
}

const styles = StyleSheet.create({
  add: {
    alignItems: "center",
    borderColor: colors.accent,
    borderRadius: radius.sm,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: space.xl,
    minHeight: 50,
  },
  back: { justifyContent: "center", minHeight: tapTarget },
  cancelDelete: { alignItems: "center", justifyContent: "center", minHeight: tapTarget },
  confirmDelete: { marginTop: space.xl },
  content: { paddingBottom: space.section, paddingHorizontal: space.xl, paddingTop: space.lg },
  delete: { marginTop: space.md },
  error: { marginTop: space.xl },
  eyebrow: { marginTop: space.xxl },
  metadata: { marginBottom: space.lg },
  metric: { backgroundColor: colors.surface, borderRadius: radius.sm, flex: 1, padding: space.md },
  metricLabel: { marginTop: space.xs },
  metricValue: { fontSize: type.heading.fontSize },
  modalBackdrop: {
    alignItems: "center",
    backgroundColor: "rgba(0, 0, 0, 0.6)",
    flex: 1,
    justifyContent: "center",
    padding: space.xl,
  },
  modalBody: { lineHeight: 21, marginTop: space.sm },
  modalCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.xl,
    width: "100%",
  },
  note: { marginTop: space.md, textAlign: "center" },
  photo: { borderRadius: radius.md, height: 260, marginBottom: space.lg, width: "100%" },
  primary: { marginTop: space.xl },
  title: { marginBottom: space.xl, marginTop: space.sm },
  totals: { flexDirection: "row", gap: space.sm, marginBottom: space.xl },
  validationError: { marginBottom: space.md },
});
