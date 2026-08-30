/**
 * `needsOnboarding`, the rule all three routing points share.
 *
 * Two cases, because onboarding is a hard gate and the rule reads one field.
 * It briefly read two, while a skip was a supported exit. The 30 Aug 2026
 * sequencing decision removed the skip, and this file shrank with it.
 */

import { describe, expect, it } from "@jest/globals";
import type { User } from "@macros/api-client";

import { needsOnboarding } from "../lib/onboarding";

const userWith = (completed: boolean): User => ({ onboarding_completed: completed }) as User;

describe("needsOnboarding", () => {
  it("is true for a user with no targets", () => {
    expect(needsOnboarding(userWith(false))).toBe(true);
  });

  it("is false once the user owns targets", () => {
    expect(needsOnboarding(userWith(true))).toBe(false);
  });
});
