/**
 * One question, asked from two places: does this user still need onboarding?
 *
 * The launch gate and the post-sign-in redirect both ask it. Before MAC-47 they
 * both read `user.onboarding_completed` inline, and the answer was wrong in the
 * same way in both files.
 *
 * A two-part condition duplicated across two screens is a bug waiting for the
 * day someone changes one of them. Neither call site can drift from the other
 * now, because there is only one copy of the rule.
 */

import type { User } from "@macros/api-client";

/**
 * True when the user has neither finished onboarding nor chosen to leave it.
 *
 * **Two fields, because they record different things.**
 *
 * `onboarding_completed` is server-derived. It turns true when the user's first
 * target version is created, and no client can write it.
 *
 * `onboarding_skipped_at` is the user's own choice, written by the client. Doc
 * 26 makes leaving onboarding early a supported end state, and without reading
 * this half the gate sends a skipper back to onboarding on every cold start.
 * The exit stops being an exit.
 *
 * Both can be set at once and that is fine. Skip on day one, set targets from
 * Settings in week two, and the pair still records what happened while this
 * function keeps returning false.
 */
export const needsOnboarding = (user: User): boolean =>
  !user.onboarding_completed && !user.onboarding_skipped_at;
