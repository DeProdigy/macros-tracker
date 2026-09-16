import { describe, expect, it } from "@jest/globals";
import type { Day } from "@macros/api-client";

import { dayProgress } from "../lib/day-progress";

function day(overrides: Partial<Day> = {}): Day {
  return {
    local_date: "2026-09-16",
    targets: { calories: 2350, protein_g: 185, fiber_g: 32 },
    calories: "1690.00",
    protein_g: "128.00",
    fiber_g: "19.00",
    entries: [],
    ...overrides,
  } as Day;
}

describe("dayProgress", () => {
  it("reports what is left when the day is under target", () => {
    const progress = dayProgress(day())!;

    expect(progress.calories.remaining).toBe(660);
    expect(progress.calories.status).toBe("under");
    expect(progress.calories.fraction).toBeCloseTo(1690 / 2350);
    expect(progress.caloriesOverFraction).toBe(0);
  });

  it("scales the calorie overage against the target, not against itself", () => {
    // The approved over-target screen draws the overage as a second arc on the
    // ring's own scale, so 310 over a 2350 target looks like 13% of a day. A
    // fraction of the overage itself would always draw a full lap and say
    // nothing about how far over the user went.
    const progress = dayProgress(day({ calories: "2660.00" }))!;

    expect(progress.calories.status).toBe("over");
    expect(progress.calories.remaining).toBe(-310);
    expect(progress.calories.fraction).toBe(1);
    expect(progress.caloriesOverFraction).toBeCloseTo(310 / 2350);
  });

  it("caps the overage arc at one full lap", () => {
    const progress = dayProgress(day({ calories: "9000.00" }))!;

    expect(progress.caloriesOverFraction).toBe(1);
  });

  it("treats passing the protein target as met, not as a warning", () => {
    // Going over on calories is a warning. Going over on protein is the goal.
    // One shared "over" meaning would tell the user the wrong thing.
    const progress = dayProgress(day({ protein_g: "191.00" }))!;

    expect(progress.protein.status).toBe("over");
    expect(progress.protein.remaining).toBe(-6);
    expect(progress.fiber.status).toBe("under");
    expect(progress.fiber.remaining).toBe(13);
  });

  it("counts landing exactly on a target as met", () => {
    const progress = dayProgress(day({ protein_g: "185.00" }))!;

    expect(progress.protein.status).toBe("met");
    expect(progress.protein.remaining).toBe(0);
    expect(progress.protein.fraction).toBe(1);
  });

  it("returns null when the day carries no targets", () => {
    // Nullable in the contract. Substituting the current target would rewrite
    // history for an old day, which capturing a TargetVersion exists to stop.
    expect(dayProgress(day({ targets: null }))).toBeNull();
  });

  it("returns null when a target is not positive", () => {
    // A zero target is "no target" wearing a number. Measuring against it
    // divides by zero, and subtracting from it reports the whole day's food as
    // calories still remaining, which reads as the exact opposite of the truth.
    expect(dayProgress(day({ targets: { calories: 0, protein_g: 185, fiber_g: 32 } }))).toBeNull();
    expect(dayProgress(day({ targets: { calories: 2350, protein_g: 0, fiber_g: 32 } }))).toBeNull();
    expect(
      dayProgress(day({ targets: { calories: 2350, protein_g: 185, fiber_g: -5 } })),
    ).toBeNull();
  });

  it("reads an empty day as nothing consumed", () => {
    const progress = dayProgress(day({ calories: "0.00", protein_g: "0.00", fiber_g: "0.00" }))!;

    expect(progress.calories.remaining).toBe(2350);
    expect(progress.calories.fraction).toBe(0);
    expect(progress.protein.status).toBe("under");
  });
});
