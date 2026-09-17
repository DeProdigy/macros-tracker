/**
 * The bug this pins: DRF renders a `DecimalField` as a full-scale string, so
 * a 130 kcal shake arrives as "130.00" and Today printed "130.00 kcal".
 *
 * The test fixtures all used short strings like "130", which is why the suites
 * never caught it. These cases use the shapes the real API actually sends.
 */

import { describe, expect, it } from "@jest/globals";

import { macroValue } from "@/lib/format";

describe("macroValue", () => {
  it("drops the decimal scale DRF sends", () => {
    expect(macroValue("130.00")).toBe("130");
    expect(macroValue("1020.00")).toBe("1,020");
    expect(macroValue("2.00")).toBe("2");
  });

  it("rounds rather than truncating", () => {
    expect(macroValue("11.60")).toBe("12");
    expect(macroValue("11.40")).toBe("11");
  });

  it("groups thousands, because a four-digit calorie count is common", () => {
    expect(macroValue("2350")).toBe("2,350");
  });

  it("accepts a number as well as a string", () => {
    expect(macroValue(540)).toBe("540");
  });

  it("shows zero rather than NaN for a value it cannot parse", () => {
    expect(macroValue("")).toBe("0");
    expect(macroValue("not a number")).toBe("0");
  });
});
