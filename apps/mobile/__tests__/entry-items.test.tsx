import { expect, it, jest } from "@jest/globals";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import type { ReactNode } from "react";

import {
  analysisItemToEditable,
  isValidEditableItem,
  itemTotals,
  itemUpdateRequest,
  itemWriteRequest,
  stepQuantity,
  useEntryItemMutations,
} from "../lib/entry-items";
import { createTestQueryClient } from "../test-utils/render";

const mockUpdateEntryItem = jest.fn();
jest.mock("@macros/api-client", () => ({
  createEntryItem: jest.fn(),
  deleteEntryItem: jest.fn(),
  getGetDayQueryKey: (date: string) => ["day", date],
  getGetEntryQueryKey: (id: number) => ["entry", id],
  updateEntryItem: (...args: unknown[]) => mockUpdateEntryItem(...args),
}));

const localDate = "2026-09-01";
const dayResponse = {
  status: 200 as const,
  headers: new Headers(),
  data: {
    local_date: localDate,
    targets: null,
    calories: "100.00",
    protein_g: "10.00",
    fiber_g: "2.00",
    entries: [
      {
        id: 7,
        source: "manual" as const,
        description: "Lunch",
        eaten_at: "2026-09-01T17:00:00Z",
        calories: "100.00",
        protein_g: "10.00",
        fiber_g: "2.00",
        photo_url: null,
        items: [
          {
            id: 9,
            name: "Chicken",
            portion_label: "1 piece",
            quantity: "1.00",
            calories: "100.00",
            protein_g: "10.00",
            fiber_g: "2.00",
          },
        ],
      },
    ],
  },
};

it("rounds combined item totals half up like the API", () => {
  expect(
    itemTotals([
      {
        clientId: "small-item",
        name: "Small item",
        portion_label: "",
        quantity: "0.10",
        calories: "0.05",
        protein_g: "0.00",
        fiber_g: "0.00",
      },
    ]),
  ).toEqual({ calories: "0.01", protein_g: "0.00", fiber_g: "0.00" });
});

it("normalizes decimal-pad shorthand and sends only changed PATCH fields", () => {
  const original = dayResponse.data.entries[0].items[0];
  const item = {
    clientId: "item-9",
    id: 9,
    name: "Chicken",
    portion_label: "1 piece",
    quantity: "1.",
    calories: "100.00",
    protein_g: ".5",
    fiber_g: "2.00",
  };

  expect(itemWriteRequest(item)).toEqual({
    name: "Chicken",
    portion_label: "1 piece",
    quantity: "1.00",
    calories: "100.00",
    protein_g: "0.50",
    fiber_g: "2.00",
  });
  expect(itemUpdateRequest(item, original)).toEqual({ protein_g: "0.50" });
});

it("steps quantities with exact hundredths and clamps invalid values", () => {
  expect(stepQuantity("2.3", -1)).toBe("1.30");
  expect(stepQuantity("1.1", -1)).toBe("0.10");
  expect(stepQuantity("1.", 1)).toBe("2.00");
  expect(stepQuantity("not-a-number", -1)).toBe("0.01");
  expect(stepQuantity("not-a-number", 1)).toBe("1.00");
  expect(stepQuantity("999999.99", 1)).toBe("999999.99");
});

it("rejects quantities that exceed the API decimal field", () => {
  expect(
    isValidEditableItem({
      clientId: "large-item",
      name: "Large item",
      portion_label: "",
      quantity: "1000000.00",
      calories: "1.00",
      protein_g: "0.00",
      fiber_g: "0.00",
    }),
  ).toBe(false);
});

it("updates cached entry and day totals immediately, then restores them on failure", async () => {
  let rejectRequest: (error: Error) => void = () => undefined;
  mockUpdateEntryItem.mockReturnValue(
    new Promise((_resolve, reject) => {
      rejectRequest = reject;
    }),
  );
  const queryClient = createTestQueryClient();
  const queryKey = ["day", localDate];
  queryClient.setQueryData(queryKey, dayResponse);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const { result, unmount } = renderHook(() => useEntryItemMutations(localDate, 7), { wrapper });

  act(() => {
    result.current.update.mutate({
      original: dayResponse.data.entries[0].items[0],
      item: {
        clientId: "item-9",
        id: 9,
        name: "Chicken",
        portion_label: "1 piece",
        quantity: "2.00",
        calories: "100.00",
        protein_g: "10.00",
        fiber_g: "2.00",
      },
    });
  });

  await waitFor(() => expect(mockUpdateEntryItem).toHaveBeenCalledWith(7, 9, { quantity: "2.00" }));
  await waitFor(() =>
    expect(queryClient.getQueryData<typeof dayResponse>(queryKey)?.data.calories).toBe("200.00"),
  );
  act(() => rejectRequest(new Error("network")));
  await waitFor(() =>
    expect(queryClient.getQueryData<typeof dayResponse>(queryKey)?.data.calories).toBe("100.00"),
  );
  await waitFor(() => expect(result.current.update.isError).toBe(true));
  unmount();
  queryClient.clear();
});

it("carries the count the analysis returned into the editable row", () => {
  // Before MAC-76 this hardcoded "1.00", because the provider schema had no
  // quantity field and the model put the count in the name instead.
  const item = analysisItemToEditable(
    {
      name: "boiled egg",
      portion: "1 egg",
      quantity: "4.00",
      calories: "78.00",
      protein_g: "6.30",
      fiber_g: "0.00",
    },
    0,
  );

  expect(item.name).toBe("boiled egg");
  expect(item.portion_label).toBe("1 egg");
  expect(item.quantity).toBe("4.00");
  // The row holds one egg. The totals multiply.
  expect(item.calories).toBe("78.00");
  expect(itemTotals([item]).calories).toBe("312.00");
});

it("totals a count the same way the API does", () => {
  /*
   * The twin of `test_totals_round_the_sum_once_rather_than_each_product` in
   * apps/api/ai/tests/test_analysis_service.py.
   *
   * Three items of 1.5 units at 1.01 kcal. Summing the exact products gives
   * 4.5450, which rounds once to 4.55. Rounding each product first gives 1.52
   * three times, which sums to 4.56. The Review screen and the saved entry show
   * the same number only while both sides pick the same order, and a penny that
   * moves when you save is the kind of bug nobody can explain.
   */
  const item = {
    clientId: "a",
    name: "sauce",
    portion_label: "1 tsp",
    quantity: "1.50",
    calories: "1.01",
    protein_g: "0.00",
    fiber_g: "0.00",
  };

  expect(itemTotals([item, { ...item, clientId: "b" }, { ...item, clientId: "c" }]).calories).toBe(
    "4.55",
  );
});
