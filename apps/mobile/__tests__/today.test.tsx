import { afterEach, beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen } from "@testing-library/react-native";
import { router } from "expo-router";

import TodayScreen from "../app/(app)/today";
import { localIsoDate } from "../lib/local-day";
import { useSession } from "../lib/session";
import { REAL_TIMERS } from "../test-utils/render";

/**
 * A fixed instant, so "today" cannot change under the test.
 *
 * The screen calls `new Date()` during render. Reading the real clock here
 * instead would leave a race: if the process crossed local midnight between
 * this file loading and a render, the expected date and the rendered one would
 * disagree. Moving the read into `beforeEach` shrinks that window without
 * closing it, because the render still happens later.
 *
 * `beforeEach` freezes only `Date`. Faking the timer functions as well makes
 * React Native Testing Library hang, and nothing here needs them faked.
 */
const NOW = new Date(2026, 8, 16, 12, 0, 0);
const today = localIsoDate(NOW);
const pastDate = "2026-08-31";
// `mock` prefix required: jest.mock factories may not close over other names.
let mockParams: { date?: string } = {};
/**
 * Build the calendar cell's label the same way `DayPicker` does.
 *
 * Not the literal "Choose August 30, 2026". `toLocaleDateString([], ...)` reads
 * the runtime's default locale, which comes from the environment, so that
 * literal only matches on an English runner. A German one produces
 * "30. August 2026" and the query finds nothing.
 *
 * Unlike the timezone, the locale cannot be pinned in `jest.global-setup.js`.
 * Node resolves its default locale before global setup runs, so a test that
 * asserts a formatted date has to build the expected string with the same
 * formatter.
 */
const chooseLabel = (date: Date) =>
  `Choose ${date.toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" })}`;

const mockUseGetDay = jest.fn();
const mockUseGetDays = jest.fn();
jest.mock("@macros/api-client", () => ({
  useGetDay: (...args: unknown[]) => mockUseGetDay(...args),
  useGetDays: (...args: unknown[]) => mockUseGetDays(...args),
}));
jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    Link: ({ children }: { children: React.ReactNode }) => <Text>{children}</Text>,
    router: { push: jest.fn(), replace: jest.fn() },
    useLocalSearchParams: () => mockParams,
  };
});
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers({ doNotFake: [...REAL_TIMERS] });
  jest.setSystemTime(NOW);
  mockParams = { date: pastDate };
  mockUseSession.mockReturnValue({
    status: "signedIn",
    timezoneStatus: "ready",
    user: { timezone: "UTC", has_logged_food: true },
  } as never);
  mockUseGetDay.mockReturnValue({
    isLoading: false,
    data: {
      status: 200,
      data: {
        local_date: pastDate,
        targets: null,
        calories: "0.00",
        protein_g: "0.00",
        fiber_g: "0.00",
        entries: [],
      },
    },
  });
  mockUseGetDays.mockReturnValue({
    data: { status: 200, data: [{ local_date: "2026-08-30" }] },
    isError: false,
  });
});

afterEach(() => {
  jest.useRealTimers();
});

describe("TodayScreen", () => {
  it("confirms the clock is frozen", () => {
    // Guards the premise. The fixed dates below would also pass on a machine
    // whose real clock sits in September 2026, so without this the freeze could
    // stop working and nothing would say so.
    expect(Date.now()).toBe(NOW.getTime());
  });

  it("tells a past empty day that backfilling is still allowed", () => {
    render(<TodayScreen />);

    expect(screen.getByText("Nothing logged this day")).toBeTruthy();
    expect(screen.getByText("You can still add food to this day.")).toBeTruthy();
    // "LOG FOOD" would read as logging it now, which is not what this writes.
    expect(screen.getByRole("button", { name: "ADD TO THIS DAY" })).toBeTruthy();
  });

  it("teaches the next action on an empty Today the user has never logged on", () => {
    mockParams = { date: today };
    mockUseSession.mockReturnValue({
      status: "signedIn",
      timezoneStatus: "ready",
      user: { timezone: "UTC", has_logged_food: false },
    } as never);

    render(<TodayScreen />);

    expect(screen.getByText("Nothing logged yet")).toBeTruthy();
    expect(
      screen.getByText("Point the camera at your food. The app fills in the numbers."),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "LOG FOOD" })).toBeTruthy();
  });

  it("stays quiet on an empty Today for a user who has logged before", () => {
    mockParams = { date: today };

    render(<TodayScreen />);

    expect(screen.getByText("Nothing logged yet")).toBeTruthy();
    // The lesson is for a first run only. Repeating it every morning is noise.
    expect(
      screen.queryByText("Point the camera at your food. The app fills in the numbers."),
    ).toBeNull();
    expect(screen.queryByText("You can still add food to this day.")).toBeNull();
  });

  it("opens the calendar and preserves the selected past day", () => {
    render(<TodayScreen />);

    fireEvent.press(screen.getByRole("button", { name: "Choose day" }));
    fireEvent.press(screen.getByRole("button", { name: chooseLabel(new Date(2026, 7, 30)) }));

    expect(router.replace).toHaveBeenCalledWith({
      pathname: "/today",
      params: { date: "2026-08-30" },
    });
  });

  it("passes the selected date into food logging", () => {
    render(<TodayScreen />);

    fireEvent.press(screen.getByRole("button", { name: "ADD TO THIS DAY" }));

    expect(router.push).toHaveBeenCalledWith({
      pathname: "/log-food",
      params: { date: pastDate },
    });
  });

  it("shows totals and entries returned by the day resource", () => {
    mockUseGetDay.mockReturnValue({
      isLoading: false,
      data: {
        status: 200,
        data: {
          local_date: "2026-08-31",
          targets: null,
          calories: "240.00",
          protein_g: "36.00",
          fiber_g: "4.00",
          entries: [
            {
              id: 1,
              description: "Greek yogurt",
              eaten_at: "2026-08-31T16:30:00Z",
              calories: "240.00",
              protein_g: "36.00",
              fiber_g: "4.00",
              source: "manual",
              items: [],
            },
          ],
        },
      },
    });
    render(<TodayScreen />);
    expect(screen.getByText("Greek yogurt")).toBeTruthy();
    expect(screen.getByText("240.00 kcal")).toBeTruthy();
    expect(screen.getByText("36.00p · 4.00f")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Edit Greek yogurt" }));
    expect(router.push).toHaveBeenCalledWith({
      pathname: "/entry/[id]",
      params: { id: 1, date: expect.any(String) },
    });
  });

  it("renders a Recent entry without a photo placeholder", () => {
    mockUseGetDay.mockReturnValue({
      isLoading: false,
      data: {
        status: 200,
        data: {
          local_date: "2026-08-31",
          targets: null,
          calories: "180.00",
          protein_g: "27.00",
          fiber_g: "3.00",
          entries: [
            {
              id: 2,
              description: "Greek yogurt",
              eaten_at: "2026-08-31T16:30:00Z",
              calories: "180.00",
              protein_g: "27.00",
              fiber_g: "3.00",
              source: "recent",
              photo_url: null,
              items: [],
            },
          ],
        },
      },
    });

    render(<TodayScreen />);

    expect(screen.getByRole("button", { name: "Edit Greek yogurt" })).toBeTruthy();
    expect(screen.queryByLabelText("Greek yogurt meal")).toBeNull();
  });

  it("shows an error without false zero totals when the day request fails", () => {
    mockUseGetDay.mockReturnValue({ isError: true, isLoading: false });

    render(<TodayScreen />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not load your day. Reopen the app to try again.",
    );
    expect(screen.queryByText("0.00")).toBeNull();
    expect(screen.queryByText("Nothing logged yet")).toBeNull();
  });
});

describe("TodayScreen progress", () => {
  function withDay(overrides: Record<string, unknown>) {
    mockUseGetDay.mockReturnValue({
      isLoading: false,
      data: {
        status: 200,
        data: {
          local_date: "2026-08-31",
          targets: { calories: 2350, protein_g: 185, fiber_g: 32 },
          calories: "1690.00",
          protein_g: "128.00",
          fiber_g: "19.00",
          entries: [],
          ...overrides,
        },
      },
    });
  }

  it("shows what is left against the day's own targets", () => {
    withDay({});
    render(<TodayScreen />);

    expect(screen.getByText("REMAINING")).toBeTruthy();
    // Asserted through the accessible label, not the visible string. The ring
    // formats with toLocaleString, so "1,690" depends on the environment's
    // locale and would make this test fail on a device that CI never sees.
    expect(screen.getByLabelText("660 kcal left. 1690 of 2350.")).toBeTruthy();
    expect(screen.getByText("57g short")).toBeTruthy();
    expect(screen.getByText("13g short")).toBeTruthy();
  });

  it("turns the calorie ring into an overage when the target is passed", () => {
    withDay({ calories: "2660.00" });
    render(<TodayScreen />);

    expect(screen.getByText("OVER BY")).toBeTruthy();
    expect(screen.getByText("310")).toBeTruthy();
    expect(screen.queryByText("REMAINING")).toBeNull();
  });

  it("treats a passed protein target as met rather than as a warning", () => {
    // The point of the per-macro rule. Over on calories warns, over on protein
    // congratulates. One shared meaning would be wrong for one of them.
    withDay({ calories: "2660.00", protein_g: "191.00" });
    render(<TodayScreen />);

    expect(screen.getByText("OVER BY")).toBeTruthy();
    expect(screen.getByText("TARGET MET")).toBeTruthy();
  });

  it("falls back to plain totals when the day carries no targets", () => {
    withDay({ targets: null });
    render(<TodayScreen />);

    expect(screen.queryByText("REMAINING")).toBeNull();
    expect(screen.queryByText("OVER BY")).toBeNull();
    expect(screen.getByText("CALORIES")).toBeTruthy();
  });
});
