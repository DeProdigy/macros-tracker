/**
 * The calendar sheet behind the date on Today.
 *
 * Three things here can be wrong without looking wrong: a future day that
 * accepts a press, a logged-day marker that reads another month's data, and a
 * marker request that fires while the sheet is closed. Each is tested.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { DayPicker } from "../components/day-picker";
import { localIsoDate } from "../lib/local-day";

const mockUseGetDays = jest.fn();
jest.mock("@macros/api-client", () => ({
  useGetDays: (...args: unknown[]) => mockUseGetDays(...args),
}));

// The zone is pinned in jest.global-setup.js, so "today" is stable per run but
// not a fixed string. The picker renders around the real current month.
const today = new Date();
const todayIso = localIsoDate(today);
const currentMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

const longDate = (date: Date) =>
  date.toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" });

const onSelect = jest.fn();
const onClose = jest.fn();

const renderPicker = (selectedDate = todayIso) =>
  render(
    <DayPicker enabled onClose={onClose} onSelect={onSelect} selectedDate={selectedDate} visible />,
  );

beforeEach(() => {
  jest.clearAllMocks();
  mockUseGetDays.mockReturnValue({ data: { status: 200, data: [] }, isError: false });
});

describe("DayPicker", () => {
  it("asks for the markers of the month it is showing", () => {
    renderPicker();

    expect(mockUseGetDays).toHaveBeenCalledWith(
      { month: currentMonth },
      { query: { enabled: true } },
    );
  });

  it("does not fetch markers while the sheet is closed", () => {
    render(
      <DayPicker
        enabled
        onClose={onClose}
        onSelect={onSelect}
        selectedDate={todayIso}
        visible={false}
      />,
    );

    // The query still mounts. `enabled: false` is what stops the request, so
    // that flag is the assertion, not the absence of a call.
    expect(mockUseGetDays).toHaveBeenCalledWith(
      { month: currentMonth },
      { query: { enabled: false } },
    );
  });

  it("reports the chosen day as a local ISO date", () => {
    renderPicker();
    const first = new Date(today.getFullYear(), today.getMonth(), 1);

    fireEvent.press(screen.getByRole("button", { name: `Choose ${longDate(first)}` }));

    expect(onSelect).toHaveBeenCalledWith(localIsoDate(first));
  });

  it("refuses a future day in the current month", () => {
    const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
    if (tomorrow.getMonth() !== today.getMonth()) {
      // On the last day of a month tomorrow is not drawn at all, which is the
      // same guarantee by a different route.
      renderPicker();
      expect(screen.queryByLabelText(`Choose ${longDate(tomorrow)}`)).toBeNull();
      return;
    }
    renderPicker();

    fireEvent.press(screen.getByRole("button", { name: `Choose ${longDate(tomorrow)}` }));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("marks the days the API says carry entries", () => {
    const second = new Date(today.getFullYear(), today.getMonth(), 2);
    mockUseGetDays.mockReturnValue({
      data: { status: 200, data: [{ local_date: localIsoDate(second) }] },
      isError: false,
    });

    renderPicker();

    expect(screen.getAllByLabelText("Contains logged food")).toHaveLength(1);
  });

  it("will not page past the current month", () => {
    renderPicker();

    fireEvent.press(screen.getByRole("button", { name: "Next month" }));

    // Still the same month, so the marker request never changed.
    expect(mockUseGetDays).toHaveBeenLastCalledWith(
      { month: currentMonth },
      { query: { enabled: true } },
    );
  });

  it("pages back and asks for the earlier month", () => {
    renderPicker();
    const previous = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const previousMonth = `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;

    fireEvent.press(screen.getByRole("button", { name: "Previous month" }));

    expect(mockUseGetDays).toHaveBeenLastCalledWith(
      { month: previousMonth },
      { query: { enabled: true } },
    );
  });

  it("says the markers failed instead of showing a month with no dots", () => {
    // A silent failure reads as "you logged nothing that month", which is worse
    // than an error: it is a wrong answer rather than a missing one.
    mockUseGetDays.mockReturnValue({ data: undefined, isError: true });

    renderPicker();

    expect(screen.getByText("Could not load logged-day markers.")).toBeTruthy();
  });
});
