import {
  ApiError,
  createEntry,
  getGetDayQueryKey,
  getGetFoodsQueryKey,
  type RecentFood,
  useGetFoods,
} from "@macros/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import {
  type EditableFoodItem,
  isValidMacroValue,
  isValidQuantityValue,
  isValidEditableItem,
  itemTotals,
  itemWriteRequest,
  stepQuantity,
} from "@/lib/entry-items";
import {
  entryTimingForDate,
  localIsoDate,
  LocalDayUnavailable,
  parseLocalIsoDate,
} from "@/lib/local-day";
import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

type LogMode = "manual" | "recents";

const recentEditableItem = (food: RecentFood, quantity: string): EditableFoodItem => ({
  clientId: `recent-${food.id}`,
  id: food.id,
  name: food.name,
  portion_label: food.portion_label ?? "",
  quantity,
  calories: food.calories,
  protein_g: food.protein_g,
  fiber_g: food.fiber_g,
});

export default function LogFoodScreen() {
  const palette = usePalette();
  const session = useSession();
  const queryClient = useQueryClient();
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const today = localIsoDate(new Date());
  const requestedDate = Array.isArray(params.date) ? params.date[0] : params.date;
  const localDate =
    requestedDate && parseLocalIsoDate(requestedDate) && requestedDate <= today
      ? requestedDate
      : today;
  const [mode, setMode] = useState<LogMode>("manual");
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [calories, setCalories] = useState("");
  const [protein, setProtein] = useState("");
  const [fiber, setFiber] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedFood, setSelectedFood] = useState<RecentFood | null>(null);
  const [recentQuantity, setRecentQuantity] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const foodsQuery = useGetFoods(debouncedSearch ? { search: debouncedSearch } : undefined, {
    query: { enabled: session.status === "signedIn" && mode === "recents" },
  });

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  if (session.status !== "signedIn") return null;

  const foods = foodsQuery.data?.status === 200 ? foodsQuery.data.data : [];
  const selectedItem = selectedFood ? recentEditableItem(selectedFood, recentQuantity) : null;
  const preview = selectedItem ? itemTotals([selectedItem]) : null;

  const switchMode = (nextMode: LogMode) => {
    setMode(nextMode);
    setError(null);
  };

  const saveManual = async () => {
    const macros = [calories, protein, fiber].map((value) => (value.trim() === "" ? "0" : value));
    if (
      !name.trim() ||
      !isValidQuantityValue(quantity) ||
      macros.some((value) => !isValidMacroValue(value)) ||
      !macros.some((value) => Number(value) > 0)
    ) {
      setError("Enter a name, a positive quantity, and at least one macro value.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const context = entryTimingForDate(session.timezoneStatus, session.user.timezone, localDate);
      const response = await createEntry({
        ...context,
        item: {
          name: name.trim(),
          quantity,
          calories: macros[0],
          protein_g: macros[1],
          fiber_g: macros[2],
        },
      });
      if (response.status !== 201) throw new Error("Save failed");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(context.local_date) }),
        queryClient.invalidateQueries({ queryKey: getGetFoodsQueryKey(), refetchType: "none" }),
      ]);
      router.replace({ pathname: "/today", params: { date: localDate } });
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

  const saveRecent = async () => {
    if (!selectedItem || !isValidEditableItem(selectedItem)) {
      setError("Enter a positive quantity.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const context = entryTimingForDate(session.timezoneStatus, session.user.timezone, localDate);
      const response = await createEntry({
        ...context,
        recent_item_id: selectedFood!.id,
        quantity: itemWriteRequest(selectedItem).quantity,
      });
      if (response.status !== 201) throw new Error("Save failed");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: getGetDayQueryKey(context.local_date) }),
        queryClient.invalidateQueries({ queryKey: getGetFoodsQueryKey(), refetchType: "none" }),
      ]);
      router.replace({ pathname: "/today", params: { date: localDate } });
    } catch (caught) {
      const missingRecentFood =
        caught instanceof ApiError &&
        caught.status === 400 &&
        typeof caught.body === "object" &&
        caught.body !== null &&
        "recent_item_id" in caught.body;
      if (missingRecentFood) {
        setSelectedFood(null);
        await queryClient.invalidateQueries({ queryKey: getGetFoodsQueryKey() });
      }
      setError(
        caught instanceof LocalDayUnavailable
          ? "Sync your timezone and try again."
          : missingRecentFood
            ? "That recent food is no longer available."
            : "Could not log this recent food. Try again.",
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
      <Text style={[styles.title, { color: palette.text }]}>Log food</Text>
      <View style={styles.choices}>
        <Choice
          label="PHOTO"
          onPress={() => router.push({ pathname: "/photo", params: { date: localDate } })}
          active={false}
        />
        <Choice label="RECENTS" onPress={() => switchMode("recents")} active={mode === "recents"} />
        <Choice label="MANUAL" onPress={() => switchMode("manual")} active={mode === "manual"} />
      </View>
      {mode === "manual" ? (
        <>
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
          {error ? <ErrorMessage message={error} color={palette.error} /> : null}
          <SaveButton saving={saving} label="SAVE FOOD" onPress={saveManual} />
        </>
      ) : (
        <>
          <TextInput
            accessibilityLabel="Search recent foods"
            value={search}
            onChangeText={(value) => {
              setSearch(value);
              setSelectedFood(null);
              setError(null);
            }}
            placeholder="Search what you've logged before"
            placeholderTextColor={palette.dimText}
            style={input}
          />
          <Text style={[styles.recentsLabel, { color: palette.secondaryText }]}>
            MOST RECENT FIRST
          </Text>
          {foodsQuery.isLoading ? (
            <Text style={[styles.message, { color: palette.secondaryText }]}>
              Loading recents...
            </Text>
          ) : null}
          {foodsQuery.isError ? (
            <View style={styles.message}>
              <Text accessibilityRole="alert" style={{ color: palette.error }}>
                Could not load your recent foods.
              </Text>
              <Pressable accessibilityRole="button" onPress={() => void foodsQuery.refetch()}>
                <Text style={[styles.retry, { color: palette.accent }]}>TRY AGAIN</Text>
              </Pressable>
            </View>
          ) : null}
          {!foodsQuery.isLoading && !foodsQuery.isError && foods.length === 0 ? (
            <View style={styles.empty}>
              <Text style={[styles.emptyTitle, { color: palette.text }]}>
                No recent foods found
              </Text>
              <Text style={[styles.emptyBody, { color: palette.secondaryText }]}>
                {search.trim()
                  ? "Try another search."
                  : "Log a food manually and it will appear here."}
              </Text>
            </View>
          ) : null}
          {foods.map((food) => {
            const selected = selectedFood?.id === food.id;
            return (
              <View
                key={food.id}
                style={[
                  styles.recentCard,
                  { borderColor: selected ? palette.accent : palette.hairline },
                ]}
              >
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`${selected ? "Collapse" : "Select"} ${food.name}`}
                  onPress={() => {
                    setSelectedFood(selected ? null : food);
                    setRecentQuantity("1");
                    setError(null);
                  }}
                  style={styles.recentHeader}
                >
                  <View style={styles.recentMain}>
                    <Text style={[styles.recentName, { color: palette.text }]}>{food.name}</Text>
                    <Text style={[styles.recentPortion, { color: palette.secondaryText }]}>
                      {food.portion_label || "1 serving"}
                    </Text>
                    <Text style={[styles.recentMacros, { color: palette.secondaryText }]}>
                      {food.calories} kcal · {food.protein_g}p · {food.fiber_g}f
                    </Text>
                  </View>
                  <Text style={[styles.expand, { color: palette.accent }]}>
                    {selected ? "−" : "+"}
                  </Text>
                </Pressable>
                {selected && preview ? (
                  <View style={styles.selection}>
                    <Text style={[styles.label, { color: palette.secondaryText }]}>QUANTITY</Text>
                    <View style={styles.quantityRow}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Decrease quantity"
                        onPress={() => setRecentQuantity(stepQuantity(recentQuantity, -1))}
                        style={[styles.stepper, { borderColor: palette.hairline }]}
                      >
                        <Text style={[styles.stepperText, { color: palette.text }]}>−</Text>
                      </Pressable>
                      <TextInput
                        accessibilityLabel="Recent quantity"
                        keyboardType="decimal-pad"
                        value={recentQuantity}
                        onChangeText={(value) => {
                          setRecentQuantity(value);
                          setError(null);
                        }}
                        style={[input, styles.quantityInput]}
                      />
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Increase quantity"
                        onPress={() => setRecentQuantity(stepQuantity(recentQuantity, 1))}
                        style={[styles.stepper, { borderColor: palette.hairline }]}
                      >
                        <Text style={[styles.stepperText, { color: palette.text }]}>+</Text>
                      </Pressable>
                    </View>
                    <View style={styles.preview}>
                      <Text style={[styles.label, { color: palette.secondaryText }]}>ADDS</Text>
                      <Text
                        accessibilityLabel="Macro preview"
                        style={[styles.previewValue, { color: palette.text }]}
                      >
                        {preview.calories} kcal · {preview.protein_g}p · {preview.fiber_g}f
                      </Text>
                    </View>
                    {error ? <ErrorMessage message={error} color={palette.error} /> : null}
                    <SaveButton saving={saving} label="LOG AGAIN" onPress={saveRecent} />
                  </View>
                ) : null}
              </View>
            );
          })}
          {error && !selectedFood ? <ErrorMessage message={error} color={palette.error} /> : null}
        </>
      )}
    </ScrollView>
  );
}

function Choice({
  label,
  onPress,
  active,
}: {
  label: string;
  onPress: () => void;
  active: boolean;
}) {
  const palette = usePalette();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[
        styles.choice,
        {
          backgroundColor: active ? palette.accent : palette.background,
          borderColor: palette.hairline,
        },
      ]}
    >
      <Text
        style={{
          color: active ? palette.background : palette.secondaryText,
          fontWeight: "800",
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function SaveButton({
  saving,
  label,
  onPress,
}: {
  saving: boolean;
  label: string;
  onPress: () => Promise<void>;
}) {
  const palette = usePalette();
  return (
    <Pressable
      accessibilityRole="button"
      disabled={saving}
      onPress={() => void onPress()}
      style={[styles.save, { backgroundColor: palette.accent }]}
    >
      <Text style={styles.saveText}>{saving ? "SAVING" : label}</Text>
    </Pressable>
  );
}

function ErrorMessage({ message, color }: { message: string; color: string }) {
  return (
    <Text accessibilityRole="alert" style={[styles.error, { color }]}>
      {message}
    </Text>
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
  choices: { flexDirection: "row", gap: 8, marginVertical: 28 },
  choice: {
    alignItems: "center",
    borderRadius: 10,
    borderWidth: 1,
    flex: 1,
    justifyContent: "center",
    minHeight: 52,
  },
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
  recentsLabel: { fontSize: 11, fontWeight: "800", letterSpacing: 1.5, marginTop: 26 },
  message: { marginTop: 24 },
  retry: { fontSize: 12, fontWeight: "800", marginTop: 12 },
  empty: { alignItems: "center", paddingVertical: 64 },
  emptyTitle: { fontSize: 20, fontWeight: "800" },
  emptyBody: { lineHeight: 21, marginTop: 8, textAlign: "center" },
  recentCard: { borderRadius: 12, borderWidth: 1, marginTop: 16, overflow: "hidden" },
  recentHeader: { alignItems: "center", flexDirection: "row", minHeight: 92, padding: 18 },
  recentMain: { flex: 1 },
  recentName: { fontSize: 18, fontWeight: "800" },
  recentPortion: { fontSize: 13, marginTop: 5 },
  recentMacros: { fontSize: 13, marginTop: 8 },
  expand: { fontSize: 26, marginLeft: 12 },
  selection: { padding: 18, paddingTop: 2 },
  quantityRow: { alignItems: "center", flexDirection: "row", gap: 10 },
  stepper: {
    alignItems: "center",
    borderRadius: 10,
    borderWidth: 1,
    height: 52,
    justifyContent: "center",
    width: 52,
  },
  stepperText: { fontSize: 24, fontWeight: "800" },
  quantityInput: { flex: 1, textAlign: "center" },
  preview: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 24,
  },
  previewValue: { fontSize: 16, fontWeight: "800" },
});
