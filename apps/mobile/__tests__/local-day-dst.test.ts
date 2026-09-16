/**
 * Day selection across a daylight-saving change.
 *
 * Separate from `local-day.test.ts` because these tests depend on the ambient
 * timezone. `jest.global-setup.js` pins the whole run to America/New_York, so
 * the transitions asserted below are real wherever the suite runs. Setting
 * `process.env.TZ` inside a test file does nothing: the runtime has cached the
 * zone before the file is evaluated.
 *
 * The bug being guarded against is quiet. `entryTimingForDate` builds a `Date`
 * at local midnight on the chosen day and then moves its clock time. On a
 * spring-forward day 02:00 does not exist, and the runtime slides to the next
 * real instant with nothing raised. If such a slide ever crossed midnight, the
 * app would save an entry stamped one day away from the day it told the server,
 * and the day totals would split across two dates.
 *
 * What stays untested: a zone that shifts its clocks at 00:00, such as
 * America/Santiago, where the midnight the helper starts from does not exist at
 * all. Jest holds one zone per run, so covering it needs a second Jest project.
 * That cost is not worth it while the app has one user in one American zone.
 */

import { describe, expect, it } from "@jest/globals";

import { entryTimingForDate, localIsoDate } from "../lib/local-day";

const ZONE = "America/New_York";
/** Clocks jump 02:00 to 03:00. That day is 23 hours long. */
const SPRING_FORWARD = "2026-03-08";
/** Clocks fall 02:00 to 01:00, so 01:30 happens twice. That day is 25 hours. */
const FALL_BACK = "2026-11-01";

describe("entry timing across a daylight-saving change", () => {
  it("confirms the pinned zone really shifts its clocks", () => {
    // Guards the premise. Without it the whole file would pass in UTC, where
    // no transition exists, and prove nothing.
    const insideDst = new Date(2026, 6, 1, 12).getTimezoneOffset();
    const outsideDst = new Date(2026, 0, 1, 12).getTimezoneOffset();

    expect(insideDst).not.toBe(outsideDst);
  });

  it.each([
    [SPRING_FORWARD, 0],
    [SPRING_FORWARD, 1],
    [SPRING_FORWARD, 2],
    [SPRING_FORWARD, 3],
    [SPRING_FORWARD, 23],
    [FALL_BACK, 0],
    [FALL_BACK, 1],
    [FALL_BACK, 2],
    [FALL_BACK, 23],
  ])("stamps %s at hour %i on the day it reports", (localDate, hour) => {
    const now = new Date(2026, 11, 20, hour, 30, 0, 0);

    const timing = entryTimingForDate("ready", ZONE, localDate, now);

    // The invariant that matters: the instant sent and the date sent agree.
    // A reader in the same zone must see the entry on the day they chose.
    expect(timing.local_date).toBe(localDate);
    expect(localIsoDate(new Date(timing.eaten_at))).toBe(localDate);
  });

  it("keeps the calendar date on the short day and the long day", () => {
    // 23 and 25 hour days are where a UTC round trip drifts by one date.
    expect(localIsoDate(new Date(2026, 2, 8, 12))).toBe(SPRING_FORWARD);
    expect(localIsoDate(new Date(2026, 10, 1, 12))).toBe(FALL_BACK);
  });

  it("resolves the repeated hour to one instant on the correct day", () => {
    // 01:30 exists twice on the fall-back day. Either instant is acceptable.
    // Landing on 31 October or 2 November is not.
    const now = new Date(2026, 11, 20, 1, 30, 0, 0);

    const timing = entryTimingForDate("ready", ZONE, FALL_BACK, now);

    expect(localIsoDate(new Date(timing.eaten_at))).toBe(FALL_BACK);
  });

  it("still refuses a future date chosen on a transition day", () => {
    // The clamp is arithmetic on strings, so a 23-hour day must not weaken it.
    const now = new Date(2026, 2, 8, 12);

    expect(() => entryTimingForDate("ready", ZONE, "2026-03-09", now)).toThrow();
  });
});
