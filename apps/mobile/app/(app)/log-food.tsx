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
import { Pressable, StyleSheet, TextInput, View } from "react-native";

import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import { Body, Caption, ErrorText, Heading, Label, Muted, Title } from "@/components/ui/text";

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
import { macroValue } from "@/lib/format";
import { colors, radius, space, tapTarget, type } from "@/lib/theme";
import { markFoodLogged, useSession } from "@/lib/session";

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
      markFoodLogged(session);
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
      markFoodLogged(session);
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

  return (
    <Screen contentStyle={styles.content} keyboard scroll>
      <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.cancel}>
        <Caption color={colors.accent}>CANCEL</Caption>
      </Pressable>
      <Label color={colors.accent} style={styles.eyebrow}>
        LOG FOOD
      </Label>
      <Title style={styles.title}>Log food</Title>
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
          <Label style={styles.label}>FOOD NAME</Label>
          <TextInput
            accessibilityLabel="Food name"
            value={name}
            onChangeText={setName}
            placeholder="Greek yogurt"
            placeholderTextColor={colors.textDim}
            style={styles.input}
          />
          <View style={styles.row}>
            <Field label="QUANTITY" value={quantity} onChange={setQuantity} />
            <Field label="CALORIES" value={calories} onChange={setCalories} />
          </View>
          <View style={styles.row}>
            <Field label="PROTEIN (G)" value={protein} onChange={setProtein} />
            <Field label="FIBER (G)" value={fiber} onChange={setFiber} />
          </View>
          {error ? <ErrorText style={styles.error}>{error}</ErrorText> : null}
          <SaveButton saving={saving} label="Save food" onPress={saveManual} />
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
            placeholderTextColor={colors.textDim}
            style={styles.input}
          />
          <Label style={styles.recentsLabel}>MOST RECENT FIRST</Label>
          {foodsQuery.isLoading ? <Muted style={styles.message}>Loading recents...</Muted> : null}
          {foodsQuery.isError ? (
            <View style={styles.message}>
              <ErrorText>Could not load your recent foods.</ErrorText>
              <Pressable
                accessibilityRole="button"
                onPress={() => void foodsQuery.refetch()}
                style={styles.retry}
              >
                <Caption color={colors.accent}>TRY AGAIN</Caption>
              </Pressable>
            </View>
          ) : null}
          {!foodsQuery.isLoading && !foodsQuery.isError && foods.length === 0 ? (
            <View style={styles.empty}>
              <Heading>No recent foods found</Heading>
              <Muted style={styles.emptyBody}>
                {search.trim()
                  ? "Try another search."
                  : "Log a food manually and it will appear here."}
              </Muted>
            </View>
          ) : null}
          {foods.map((food) => {
            const selected = selectedFood?.id === food.id;
            return (
              <View
                key={food.id}
                style={[styles.recentCard, selected ? styles.recentCardSelected : null]}
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
                    <Heading>{food.name}</Heading>
                    <Caption style={styles.recentPortion}>
                      {food.portion_label || "1 serving"}
                    </Caption>
                    <Caption style={styles.recentMacros}>
                      {macroValue(food.calories)} kcal · {macroValue(food.protein_g)}p ·{" "}
                      {macroValue(food.fiber_g)}f
                    </Caption>
                  </View>
                  <Heading color={colors.accent} style={styles.expand}>
                    {selected ? "−" : "+"}
                  </Heading>
                </Pressable>
                {selected && preview ? (
                  <View style={styles.selection}>
                    <Label style={styles.label}>QUANTITY</Label>
                    <View style={styles.quantityRow}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Decrease quantity"
                        onPress={() => setRecentQuantity(stepQuantity(recentQuantity, -1))}
                        style={styles.stepper}
                      >
                        <Heading>−</Heading>
                      </Pressable>
                      <TextInput
                        accessibilityLabel="Recent quantity"
                        returnKeyType="done"
                        keyboardType="decimal-pad"
                        value={recentQuantity}
                        onChangeText={(value) => {
                          setRecentQuantity(value);
                          setError(null);
                        }}
                        style={[styles.input, styles.quantityInput]}
                      />
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="Increase quantity"
                        onPress={() => setRecentQuantity(stepQuantity(recentQuantity, 1))}
                        style={styles.stepper}
                      >
                        <Heading>+</Heading>
                      </Pressable>
                    </View>
                    <View style={styles.preview}>
                      <Label>ADDS</Label>
                      <Body accessibilityLabel="Macro preview" style={styles.previewValue}>
                        {macroValue(preview.calories)} kcal · {macroValue(preview.protein_g)}p ·{" "}
                        {macroValue(preview.fiber_g)}f
                      </Body>
                    </View>
                    {error ? <ErrorText style={styles.error}>{error}</ErrorText> : null}
                    <SaveButton saving={saving} label="Log again" onPress={saveRecent} />
                  </View>
                ) : null}
              </View>
            );
          })}
          {error && !selectedFood ? <ErrorText style={styles.error}>{error}</ErrorText> : null}
        </>
      )}
    </Screen>
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
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[styles.choice, active ? styles.choiceActive : null]}
    >
      <Caption color={active ? colors.background : colors.textSecondary}>{label}</Caption>
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
  return <Button busy={saving} onPress={() => void onPress()} style={styles.save} title={label} />;
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.field}>
      <Label style={styles.label}>{label}</Label>
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
  cancel: { justifyContent: "center", minHeight: tapTarget },
  choice: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: radius.sm,
    borderWidth: 1,
    flex: 1,
    justifyContent: "center",
    minHeight: 52,
  },
  choiceActive: { backgroundColor: colors.accent },
  choices: { flexDirection: "row", gap: space.sm, marginVertical: space.xxl },
  content: { paddingBottom: space.section, paddingHorizontal: space.xl, paddingTop: space.lg },
  empty: { alignItems: "center", paddingVertical: space.empty },
  emptyBody: { marginTop: space.sm, textAlign: "center" },
  error: { marginTop: space.lg },
  expand: { marginLeft: space.md },
  eyebrow: { marginTop: space.xxl },
  field: { flex: 1 },
  input: {
    ...type.body,
    borderColor: colors.border,
    borderRadius: radius.sm,
    borderWidth: 1,
    color: colors.text,
    minHeight: 52,
    paddingHorizontal: space.md,
  },
  label: { marginBottom: space.sm },
  message: { marginTop: space.xl },
  preview: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: space.xl,
  },
  previewValue: { fontFamily: type.heading.fontFamily },
  quantityInput: { flex: 1, textAlign: "center" },
  quantityRow: { alignItems: "center", flexDirection: "row", gap: space.sm },
  recentCard: {
    borderColor: colors.border,
    borderRadius: radius.md,
    borderWidth: 1,
    marginTop: space.lg,
    overflow: "hidden",
  },
  recentCardSelected: { borderColor: colors.accent },
  recentHeader: { alignItems: "center", flexDirection: "row", minHeight: 92, padding: space.lg },
  recentMacros: { marginTop: space.sm },
  recentMain: { flex: 1 },
  recentPortion: { marginTop: space.xs },
  recentsLabel: { marginTop: space.xl },
  retry: { justifyContent: "center", minHeight: tapTarget },
  row: { flexDirection: "row", gap: space.md, marginTop: space.xl },
  save: { marginTop: space.xxl },
  selection: { padding: space.lg, paddingTop: 2 },
  title: { marginTop: space.sm },
  stepper: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: radius.sm,
    borderWidth: 1,
    height: 52,
    justifyContent: "center",
    width: 52,
  },
});
