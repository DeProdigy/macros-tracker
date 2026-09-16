/**
 * Turn a day's totals and targets into what the Today screen draws.
 *
 * This is separate from the screen because it is the part with rules. Whether
 * 191g of protein against a 185g target reads as a warning or a win is a product
 * decision, and a product decision deserves a test that names it. Rendering does
 * not.
 *
 * The API sends consumed macros as strings, because the server stores them as
 * decimals and `DecimalField` serialises exactly rather than through a float.
 * Targets arrive as integers. Both get parsed here, once.
 */

import type { Day } from "@macros/api-client";

/** How a macro stands against its target. */
export type MacroStatus = "under" | "met" | "over";

export type MacroProgress = {
  consumed: number;
  target: number;
  /** Positive when there is still room, negative once the target is passed. */
  remaining: number;
  /** Consumed over target, clamped to 1. Drives the bar and the ring arc. */
  fraction: number;
  status: MacroStatus;
};

export type DayProgress = {
  calories: MacroProgress;
  protein: MacroProgress;
  fiber: MacroProgress;
  /** How far past target the calories went, as a fraction of the same target.
   *
   * The approved over-target screen draws the overage as a second arc on the
   * same scale as the ring itself, so 310 over a 2350 target reads as 13% of a
   * day rather than as a second full lap. Keeping that on the target's scale is
   * the whole point, so it is computed here and not in the component.
   */
  caloriesOverFraction: number;
};

function toNumber(value: string | number): number {
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function macro(consumedRaw: string | number, targetRaw: number): MacroProgress {
  const consumed = toNumber(consumedRaw);
  const target = toNumber(targetRaw);
  // A zero or missing target cannot be measured against. Report it as under
  // with an empty bar rather than dividing by zero and rendering NaN.
  const fraction = target > 0 ? Math.min(consumed / target, 1) : 0;
  const remaining = target - consumed;
  const status: MacroStatus =
    target <= 0 ? "under" : consumed > target ? "over" : consumed === target ? "met" : "under";
  return { consumed, target, remaining, fraction, status };
}

/**
 * Returns null when the day carries no targets.
 *
 * `Day.targets` is nullable in the contract. It is null for a logged day whose
 * target version went missing, which the API cannot invent a replacement for.
 * The screen shows the totals and no progress in that case, because there is
 * nothing to measure against. Inventing the current target would silently
 * rewrite history for an old day, which is exactly what capturing a
 * TargetVersion per day exists to prevent.
 */
export function dayProgress(day: Day): DayProgress | null {
  if (!day.targets) return null;
  const calories = macro(day.calories, day.targets.calories);
  return {
    calories,
    protein: macro(day.protein_g, day.targets.protein_g),
    fiber: macro(day.fiber_g, day.targets.fiber_g),
    caloriesOverFraction:
      calories.target > 0 && calories.remaining < 0
        ? Math.min(-calories.remaining / calories.target, 1)
        : 0,
  };
}
