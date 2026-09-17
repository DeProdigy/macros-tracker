import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { router } from "expo-router";

import EntryEditorScreen from "../app/(app)/entry/[id]";
import { useSession } from "../lib/session";

const mockUseGetEntry = jest.fn();
const mockCreateEntry = jest.fn<(...args: unknown[]) => Promise<{ status: number }>>();
const mockDeleteEntry = jest.fn<(...args: unknown[]) => Promise<{ status: number }>>();
const mockInvalidateQueries = jest.fn<() => Promise<void>>();
const mockRemoveQueries = jest.fn();
const mockParams = jest.fn(() => ({ id: "7", date: "2026-09-01" }));
const mockUpdate = jest.fn<() => Promise<void>>();
const mockCreate = jest.fn<() => Promise<void>>();
const mockRemove = jest.fn<() => Promise<void>>();

jest.mock("@macros/api-client", () => ({
  createEntry: (...args: unknown[]) => mockCreateEntry(...args),
  deleteEntry: (...args: unknown[]) => mockDeleteEntry(...args),
  getGetDayQueryKey: (date: string) => ["day", date],
  getGetEntryQueryKey: (id: number) => ["entry", id],
  getGetFoodsQueryKey: () => ["foods"],
  useGetEntry: (...args: unknown[]) => mockUseGetEntry(...args),
}));
jest.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
    removeQueries: mockRemoveQueries,
  }),
}));
jest.mock("expo-router", () => ({
  router: { replace: jest.fn() },
  useLocalSearchParams: () => mockParams(),
}));
jest.mock("../lib/local-day", () => ({
  entryTimingForDate: () => ({
    eaten_at: "2026-09-15T16:30:00Z",
    local_date: "2026-09-15",
    timezone: "UTC",
  }),
  localIsoDate: () => "2026-09-15",
  parseLocalIsoDate: (value: string) => (value === "not-a-date" ? null : new Date(2026, 8, 1)),
}));
jest.mock("../lib/entry-items", () => {
  const actual = jest.requireActual<typeof import("../lib/entry-items")>("../lib/entry-items");
  return {
    ...actual,
    useEntryItemMutations: () => ({
      create: { isPending: false, mutateAsync: mockCreate },
      update: { isPending: false, mutateAsync: mockUpdate },
      remove: { isPending: false, mutateAsync: mockRemove },
    }),
  };
});
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

const entryQueryResult = (source = "photo", photoUrl: string | null = null) => ({
  isLoading: false,
  data: {
    status: 200,
    data: {
      id: 7,
      source,
      description: "Lunch",
      eaten_at: "2026-09-01T17:00:00Z",
      calories: "280",
      protein_g: "30.00",
      fiber_g: "4.00",
      photo_url: photoUrl,
      items: [
        {
          id: 9,
          name: "Chicken",
          portion_label: "1 piece",
          quantity: "1.00",
          calories: "180.00",
          protein_g: "20.00",
          fiber_g: "0.00",
        },
        {
          id: 10,
          name: "Rice",
          portion_label: "1 cup",
          quantity: "1.00",
          calories: "100.00",
          protein_g: "10.00",
          fiber_g: "4.00",
        },
      ],
    },
  },
});

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    timezoneStatus: "ready",
    user: { timezone: "UTC" },
  } as never);
  mockUpdate.mockResolvedValue(undefined);
  mockCreate.mockResolvedValue(undefined);
  mockRemove.mockResolvedValue(undefined);
  mockCreateEntry.mockResolvedValue({ status: 201 });
  mockDeleteEntry.mockResolvedValue({ status: 204 });
  mockInvalidateQueries.mockResolvedValue(undefined);
  mockUseGetEntry.mockReturnValue(entryQueryResult());
  mockParams.mockReturnValue({ id: "7", date: "2026-09-01" });
});

describe("EntryEditorScreen", () => {
  it("renders and edits a no-photo Recent entry", () => {
    mockUseGetEntry.mockReturnValue(entryQueryResult("recent"));

    render(<EntryEditorScreen />);

    expect(screen.getByText("Lunch")).toBeTruthy();
    expect(screen.getByLabelText("Item 1 food name").props.value).toBe("Chicken");
    expect(screen.getByText("280")).toBeTruthy();
    expect(screen.getByText(/RECENT/)).toBeTruthy();
  });

  it("saves an edited item through the item mutation", async () => {
    render(<EntryEditorScreen />);

    fireEvent.changeText(screen.getByLabelText("Item 1 food name"), "Chicken thigh");
    fireEvent.changeText(screen.getByLabelText("Item 1 quantity"), "2.00");
    fireEvent.press(screen.getAllByRole("button", { name: "SAVE CHANGES" })[0]);

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({
          original: expect.objectContaining({ id: 9, name: "Chicken" }),
          item: expect.objectContaining({ id: 9, name: "Chicken thigh", quantity: "2.00" }),
        }),
      ),
    );
  });

  it("does not send an update when the item is unchanged", () => {
    render(<EntryEditorScreen />);

    fireEvent.press(screen.getAllByRole("button", { name: "SAVE CHANGES" })[0]);

    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it("keeps an unsaved item draft when another query result arrives", () => {
    const { rerender } = render(<EntryEditorScreen />);

    fireEvent.changeText(screen.getByLabelText("Item 2 food name"), "Brown rice");
    mockUseGetEntry.mockReturnValue(entryQueryResult());
    rerender(<EntryEditorScreen />);

    expect(screen.getByLabelText("Item 2 food name").props.value).toBe("Brown rice");
  });

  it("adds a missed item and removes an existing item", async () => {
    render(<EntryEditorScreen />);

    fireEvent.press(screen.getByRole("button", { name: "ADD MISSED ITEM" }));
    fireEvent.changeText(screen.getByLabelText("New item food name"), "Avocado");
    fireEvent.changeText(screen.getByLabelText("New item calories"), "120");
    fireEvent.press(screen.getByRole("button", { name: "ADD ITEM" }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());

    fireEvent.press(screen.getAllByRole("button", { name: "REMOVE" })[0]);
    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith(9));
  });

  it("shows the retained photo when the entry has one", () => {
    mockUseGetEntry.mockReturnValue(entryQueryResult("photo", "https://example.com/meal.jpg"));

    render(<EntryEditorScreen />);

    expect(screen.getByLabelText("Lunch meal").props.source).toEqual({
      uri: "https://example.com/meal.jpg",
    });
  });

  it("logs a fresh copy to Today without photo analysis", async () => {
    render(<EntryEditorScreen />);

    fireEvent.press(screen.getByRole("button", { name: "Log again" }));

    await waitFor(() =>
      expect(mockCreateEntry).toHaveBeenCalledWith({
        eaten_at: "2026-09-15T16:30:00Z",
        local_date: "2026-09-15",
        timezone: "UTC",
        source_entry_id: 7,
      }),
    );
    expect(router.replace).toHaveBeenCalledWith({
      pathname: "/today",
      params: { date: "2026-09-15" },
    });
  });

  it("confirms deletion and returns to the source day", async () => {
    render(<EntryEditorScreen />);

    fireEvent.press(screen.getByRole("button", { name: "Delete entry" }));
    expect(screen.getByText("This removes Lunch and 280 calories from this day.")).toBeTruthy();
    expect(screen.queryByText(/streak/i)).toBeNull();
    fireEvent.press(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(mockDeleteEntry).toHaveBeenCalledWith(7));
    expect(mockRemoveQueries).toHaveBeenCalledWith({ queryKey: ["entry", 7] });
    expect(router.replace).toHaveBeenCalledWith({
      pathname: "/today",
      params: { date: "2026-09-01" },
    });
  });

  it("falls back to Today when the source date is invalid", () => {
    mockParams.mockReturnValue({ id: "7", date: "not-a-date" });
    render(<EntryEditorScreen />);

    fireEvent.press(screen.getByRole("button", { name: "BACK TO TODAY" }));

    expect(router.replace).toHaveBeenCalledWith({
      pathname: "/today",
      params: { date: "2026-09-15" },
    });
  });
});
