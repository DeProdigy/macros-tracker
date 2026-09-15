import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import EntryEditorScreen from "../app/(app)/entry/[id]";
import { useSession } from "../lib/session";

const mockUseGetDay = jest.fn();
const mockUpdate = jest.fn<() => Promise<void>>();
const mockCreate = jest.fn<() => Promise<void>>();
const mockRemove = jest.fn<() => Promise<void>>();

jest.mock("@macros/api-client", () => ({
  useGetDay: (...args: unknown[]) => mockUseGetDay(...args),
}));
jest.mock("expo-router", () => ({
  router: { back: jest.fn() },
  useLocalSearchParams: () => ({ id: "7", date: "2026-09-01" }),
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

const dayQueryResult = () => ({
  isLoading: false,
  data: {
    status: 200,
    data: {
      local_date: "2026-09-01",
      targets: null,
      calories: "280.00",
      protein_g: "30.00",
      fiber_g: "4.00",
      entries: [
        {
          id: 7,
          source: "photo",
          description: "Lunch",
          eaten_at: "2026-09-01T17:00:00Z",
          calories: "280.00",
          protein_g: "30.00",
          fiber_g: "4.00",
          photo_url: null,
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
  mockUseGetDay.mockReturnValue(dayQueryResult());
});

describe("EntryEditorScreen", () => {
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

  it("keeps an unsaved item draft when another query result arrives", () => {
    const { rerender } = render(<EntryEditorScreen />);

    fireEvent.changeText(screen.getByLabelText("Item 2 food name"), "Brown rice");
    mockUseGetDay.mockReturnValue(dayQueryResult());
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
});
