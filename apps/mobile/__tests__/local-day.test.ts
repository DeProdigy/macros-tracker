import { afterEach, describe, expect, it, jest } from "@jest/globals";

import {
  deviceTimezone,
  localDayContext,
  localIsoDate,
  LocalDayUnavailable,
} from "../lib/local-day";

const timezoneSpy = (timezone: string | undefined) =>
  jest.spyOn(Intl, "DateTimeFormat").mockReturnValue({
    resolvedOptions: () => ({ timeZone: timezone }),
  } as Intl.DateTimeFormat);

afterEach(() => {
  jest.restoreAllMocks();
});

describe("deviceTimezone", () => {
  it.each(["America/New_York", "Pacific/Auckland", "UTC"])(
    "returns the IANA name %s",
    (timezone) => {
      timezoneSpy(timezone);
      expect(deviceTimezone()).toBe(timezone);
    },
  );

  it.each(["-04:00", "GMT+12", undefined])("refuses an offset or missing name", (timezone) => {
    timezoneSpy(timezone);
    expect(deviceTimezone()).toBeNull();
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
});
