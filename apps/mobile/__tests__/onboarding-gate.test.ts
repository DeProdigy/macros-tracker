/**
 * `needsOnboarding`, the rule both routing screens share.
 *
 * Four cases, because the rule reads two independent fields and the truth
 * table is the whole function. The bug MAC-47 fixes lives in exactly one cell
 * of it: skipped but not completed, which the old inline check sent back to
 * onboarding on every cold start.
 */

import { describe, expect, it } from "@jest/globals";
import type { User } from "@macros/api-client";

import { needsOnboarding } from "../lib/onboarding";

const userWith = (completed: boolean, skippedAt: string | null): User =>
  ({ onboarding_completed: completed, onboarding_skipped_at: skippedAt }) as User;

describe("needsOnboarding", () => {
  it("is true for a user who has neither finished nor left", () => {
    expect(needsOnboarding(userWith(false, null))).toBe(true);
  });

  it("is false once the user owns targets", () => {
    expect(needsOnboarding(userWith(true, null))).toBe(false);
  });

  it("is false for a user who chose to leave without targets", () => {
    // The cell the old check got wrong. Reading `onboarding_completed` alone
    // routes this user back to onboarding forever, and doc 26 calls leaving a
    // supported end state.
    expect(needsOnboarding(userWith(false, "2026-08-30T12:00:00Z"))).toBe(false);
  });

  it("is false for a user who skipped first and set targets later", () => {
    // Both fields set is a normal history, not a contradiction: skip on day
    // one, set targets from Settings in week two. The pair still records what
    // happened.
    expect(needsOnboarding(userWith(true, "2026-08-30T12:00:00Z"))).toBe(false);
  });
});
