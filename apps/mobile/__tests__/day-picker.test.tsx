/**
 * The calendar sheet behind the date on Today.
 *
 * Three things here can be wrong without looking wrong: a future day that
 * accepts a press, a logged-day marker that reads another month's data, and a
 * marker request that fires while the sheet is closed. Each is tested.
 */

import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { DayPicker } from "../components/day-picker";
import { localIsoDate } from "../lib/local-day";
import { REAL_TIMERS } from "../test-utils/render";

const mockUseGetDays = jest.fn();
jest.mock("@macros/api-client", () => ({
  useGetDays: (...args: unknown[]) => mockUseGetDays(...args),
}));

/**
 * A fixed instant, so "today" cannot change under the test.
 *
 * `DayPicker` calls `new Date()` during render to decide which days are in the
 * future. Reading the real clock here would leave a race across local midnight,
 * and across a month boundary the picker would open on a different month than
 * the one asserted. `beforeEach` freezes `Date` to this value.
 *
 * Mid-month on purpose. The 16th leaves a real previous month to page back to
 * and a real tomorrow to refuse, with no boundary special cases.
 */
const NOW = new Date(2026, 8, 16, 12, 0, 0);
const todayIso = localIsoDate(NOW);
const currentMonth = "2026-09";

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
  jest.useFakeTimers({ doNotFake: [...REAL_TIMERS] });
  jest.setSystemTime(NOW);
  mockUseGetDays.mockReturnValue({ data: { status: 200, data: [] }, isError: false });
});

afterEach(() => {
  jest.useRealTimers();
});

describe("DayPicker", () => {
  it("confirms the clock is frozen", () => {
    // Guards the premise. The fixed dates below would also pass on a machine
    // whose real clock sits in September 2026, so without this the freeze could
    // stop working and nothing would say so.
    expect(Date.now()).toBe(NOW.getTime());
  });

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
    const first = new Date(2026, 8, 1);

    fireEvent.press(screen.getByRole("button", { name: `Choose ${longDate(first)}` }));

    expect(onSelect).toHaveBeenCalledWith(localIsoDate(first));
  });

  it("refuses a future day in the current month", () => {
    const tomorrow = new Date(2026, 8, 17);
    renderPicker();

    fireEvent.press(screen.getByRole("button", { name: `Choose ${longDate(tomorrow)}` }));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("marks the days the API says carry entries", () => {
    const second = new Date(2026, 8, 2);
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

    fireEvent.press(screen.getByRole("button", { name: "Previous month" }));

    expect(mockUseGetDays).toHaveBeenLastCalledWith(
      { month: "2026-08" },
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
