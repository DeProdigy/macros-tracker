import {
  createEntryItem,
  deleteEntryItem,
  getGetDayQueryKey,
  type Day,
  type FoodAnalysisItem,
  type FoodEntry,
  type FoodItem,
  type FoodItemWriteRequest,
  type getDayResponse,
  type PatchedFoodItemUpdateRequest,
  updateEntryItem,
} from "@macros/api-client";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export type EditableFoodItem = {
  clientId: string;
  id?: number;
  name: string;
  portion_label: string;
  quantity: string;
  calories: string;
  protein_g: string;
  fiber_g: string;
};

export const analysisItemToEditable = (
  item: FoodAnalysisItem,
  index: number,
): EditableFoodItem => ({
  clientId: `analysis-${index}`,
  name: item.name,
  portion_label: item.portion,
  quantity: "1.00",
  calories: item.calories,
  protein_g: item.protein_g,
  fiber_g: item.fiber_g,
});

export const foodItemToEditable = (item: FoodItem): EditableFoodItem => ({
  clientId: `item-${item.id}`,
  id: item.id,
  name: item.name,
  portion_label: item.portion_label ?? "",
  quantity: item.quantity,
  calories: item.calories,
  protein_g: item.protein_g,
  fiber_g: item.fiber_g,
});

export const emptyEditableItem = (clientId: string): EditableFoodItem => ({
  clientId,
  name: "",
  portion_label: "",
  quantity: "1.00",
  calories: "",
  protein_g: "",
  fiber_g: "",
});

const decimalPattern = /^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/;
const maximumQuantityHundredths = 99_999_999n;
const maximumMacroHundredths = 9_999_999_999n;

const parseHundredths = (value: string): bigint | null => {
  if (!decimalPattern.test(value)) return null;
  const withLeadingZero = value.startsWith(".") ? `0${value}` : value;
  const [whole, fraction = ""] = withLeadingZero.split(".");
  return BigInt(whole || "0") * 100n + BigInt(fraction.padEnd(2, "0"));
};

export const isValidQuantityValue = (value: string): boolean => {
  const hundredths = parseHundredths(value);
  return hundredths !== null && hundredths > 0n && hundredths <= maximumQuantityHundredths;
};

export const isValidMacroValue = (value: string): boolean => {
  const hundredths = parseHundredths(value);
  return hundredths !== null && hundredths >= 0n && hundredths <= maximumMacroHundredths;
};

const normalizeDecimal = (value: string, fallback = "0"): string => {
  const trimmed = value.trim() || fallback;
  const withLeadingZero = trimmed.startsWith(".") ? `0${trimmed}` : trimmed;
  const [whole, fraction = ""] = withLeadingZero.split(".");
  return `${whole}.${fraction.padEnd(2, "0")}`;
};

export const isValidEditableItem = (item: EditableFoodItem): boolean => {
  const macros = [item.calories, item.protein_g, item.fiber_g].map((value) =>
    value.trim() === "" ? "0" : value,
  );
  return (
    item.name.trim().length > 0 &&
    isValidQuantityValue(item.quantity) &&
    macros.every(isValidMacroValue) &&
    macros.some((value) => Number(value) > 0)
  );
};

export const itemWriteRequest = (item: EditableFoodItem): FoodItemWriteRequest => ({
  name: item.name.trim(),
  portion_label: item.portion_label.trim(),
  quantity: normalizeDecimal(item.quantity),
  calories: normalizeDecimal(item.calories),
  protein_g: normalizeDecimal(item.protein_g),
  fiber_g: normalizeDecimal(item.fiber_g),
});

const writableFields = [
  "name",
  "portion_label",
  "quantity",
  "calories",
  "protein_g",
  "fiber_g",
] as const;

export const itemUpdateRequest = (
  item: EditableFoodItem,
  original: FoodItem,
): PatchedFoodItemUpdateRequest => {
  const updated = itemWriteRequest(item);
  const previous = itemWriteRequest(foodItemToEditable(original));
  return Object.fromEntries(
    writableFields
      .filter((field) => updated[field] !== previous[field])
      .map((field) => [field, updated[field]]),
  );
};

const decimalHundredths = (value: string): bigint => {
  return parseHundredths(value) ?? 0n;
};

const formatHundredths = (value: bigint): string => {
  const whole = value / 100n;
  const fraction = (value % 100n).toString().padStart(2, "0");
  return `${whole}.${fraction}`;
};

export const stepQuantity = (value: string, direction: -1 | 1): string => {
  const current = parseHundredths(value) ?? 0n;
  const next = current + BigInt(direction) * 100n;
  const clamped =
    next < 1n ? 1n : next > maximumQuantityHundredths ? maximumQuantityHundredths : next;
  return formatHundredths(clamped);
};

export const itemTotals = (items: EditableFoodItem[]) => {
  const total = (field: "calories" | "protein_g" | "fiber_g") => {
    const productHundredths = items.reduce(
      (sum, item) => sum + decimalHundredths(item.quantity) * decimalHundredths(item[field]),
      0n,
    );
    return formatHundredths((productHundredths + 50n) / 100n);
  };
  return { calories: total("calories"), protein_g: total("protein_g"), fiber_g: total("fiber_g") };
};

const recalculateDay = (day: Day, entryId: number, items: FoodItem[]): Day => {
  const itemForms = items.map(foodItemToEditable);
  const totals = itemTotals(itemForms);
  const entries = day.entries.map((entry) =>
    entry.id === entryId ? { ...entry, ...totals, items } : entry,
  );
  const dayTotal = (field: "calories" | "protein_g" | "fiber_g") =>
    formatHundredths(entries.reduce((sum, entry) => sum + decimalHundredths(entry[field]), 0n));
  return {
    ...day,
    entries,
    calories: dayTotal("calories"),
    protein_g: dayTotal("protein_g"),
    fiber_g: dayTotal("fiber_g"),
  };
};

const updateCachedItems = (
  response: getDayResponse | undefined,
  entryId: number,
  change: (entry: FoodEntry) => FoodItem[],
): getDayResponse | undefined => {
  if (!response || response.status !== 200) return response;
  const entry = response.data.entries.find((candidate) => candidate.id === entryId);
  if (!entry) return response;
  return { ...response, data: recalculateDay(response.data, entryId, change(entry)) };
};

type MutationContext = { previous?: getDayResponse };

export function useEntryItemMutations(localDate: string, entryId: number) {
  const queryClient = useQueryClient();
  const queryKey = getGetDayQueryKey(localDate);
  const prepare = async (change: (entry: FoodEntry) => FoodItem[]): Promise<MutationContext> => {
    await queryClient.cancelQueries({ queryKey });
    const previous = queryClient.getQueryData<getDayResponse>(queryKey);
    queryClient.setQueryData<getDayResponse>(queryKey, (current) =>
      updateCachedItems(current, entryId, change),
    );
    return { previous };
  };
  const restore = (_error: Error, _variables: unknown, context?: MutationContext) => {
    if (context?.previous) queryClient.setQueryData(queryKey, context.previous);
  };
  const settle = () => queryClient.invalidateQueries({ queryKey });

  const create = useMutation({
    mutationFn: (item: EditableFoodItem) => createEntryItem(entryId, itemWriteRequest(item)),
    onMutate: (item) =>
      prepare((entry) => [...entry.items, { id: -Date.now(), ...itemWriteRequest(item) }]),
    onError: restore,
    onSettled: settle,
  });
  const update = useMutation({
    mutationFn: ({ item, original }: { item: EditableFoodItem; original: FoodItem }) =>
      updateEntryItem(entryId, original.id, itemUpdateRequest(item, original)),
    onMutate: ({ item, original }) =>
      prepare((entry) =>
        entry.items.map((current) =>
          current.id === original.id
            ? { ...current, ...itemUpdateRequest(item, original) }
            : current,
        ),
      ),
    onError: restore,
    onSettled: settle,
  });
  const remove = useMutation({
    mutationFn: (itemId: number) => deleteEntryItem(entryId, itemId),
    onMutate: (itemId) => prepare((entry) => entry.items.filter((item) => item.id !== itemId)),
    onError: restore,
    onSettled: settle,
  });

  return { create, update, remove };
}
