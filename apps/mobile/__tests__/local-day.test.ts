import { afterEach, describe, expect, it, jest } from "@jest/globals";

import {
  deviceTimezone,
  entryTimingForDate,
  localDayContext,
  localIsoDate,
  LocalDayUnavailable,
  parseLocalIsoDate,
} from "../lib/local-day";

const timezoneSpy = (timezone: string | undefined) =>
  jest.spyOn(Intl, "DateTimeFormat").mockReturnValue({
    resolvedOptions: () => ({ timeZone: timezone }),
  } as Intl.DateTimeFormat);

afterEach(() => {
  jest.restoreAllMocks();
});

describe("deviceTimezone", () => {
  it.each(["America/New_York", "Pacific/Auckland", "UTC", "Singapore", "Japan", "EST"])(
    "returns the IANA name %s",
    (timezone) => {
      timezoneSpy(timezone);
      expect(deviceTimezone()).toBe(timezone);
    },
  );

  it.each(["", undefined])("refuses a missing name", (timezone) => {
    timezoneSpy(timezone);
    expect(deviceTimezone()).toBeNull();
  });

  it("leaves timezone validation to the API", () => {
    timezoneSpy("-04:00");
    expect(deviceTimezone()).toBe("-04:00");
  });
});

describe("local dates", () => {
  it("uses calendar fields without a UTC conversion", () => {
    const local = {
      getFullYear: () => 2026,
      getMonth: () => 8,
      getDate: () => 1,
    } as Date;

    expect(localIsoDate(local)).toBe("2026-09-01");
  });

  it("builds a ready request context with the synchronized IANA name", () => {
    const local = {
      getFullYear: () => 2026,
      getMonth: () => 2,
      getDate: () => 8,
    } as Date;

    expect(localDayContext("ready", "America/New_York", local)).toEqual({
      local_date: "2026-03-08",
      timezone: "America/New_York",
    });
  });

  it.each(["syncing", "unavailable"] as const)(
    "refuses day work while timezone synchronization is %s",
    (status) => {
      expect(() => localDayContext(status, "UTC")).toThrow(LocalDayUnavailable);
    },
  );

  it("parses valid local dates and rejects impossible dates", () => {
    expect(localIsoDate(parseLocalIsoDate("2026-09-01")!)).toBe("2026-09-01");
    expect(parseLocalIsoDate("2026-02-30")).toBeNull();
    expect(parseLocalIsoDate("09/01/2026")).toBeNull();
  });

  it("combines a selected past date with the current local clock time", () => {
    const now = new Date(2026, 8, 15, 14, 30, 45, 123);
    const expected = new Date(2026, 8, 1, 14, 30, 45, 123);

    expect(entryTimingForDate("ready", "America/New_York", "2026-09-01", now)).toEqual({
      eaten_at: expected.toISOString(),
      local_date: "2026-09-01",
      timezone: "America/New_York",
    });
  });

  it("refuses future and invalid selected dates", () => {
    const now = new Date(2026, 8, 15, 12);
    expect(() => entryTimingForDate("ready", "UTC", "2026-09-16", now)).toThrow(
      LocalDayUnavailable,
    );
    expect(() => entryTimingForDate("ready", "UTC", "bad-date", now)).toThrow(LocalDayUnavailable);
  });
});
