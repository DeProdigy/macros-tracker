/**
 * One question, asked from three places: may this user be in the app yet?
 *
 * The launch gate, the post-sign-in redirect, and the guard on every signed-in
 * route all ask it. Before MAC-47 the first two asked it inline and the third
 * did not ask at all.
 *
 * One field today, so the function looks thin. It is still worth having. Three
 * inline copies is a bug waiting for the day someone changes one of them, and
 * this rule has already changed once: it briefly read two fields, while
 * onboarding was skippable.
 */

import type { User } from "@macros/api-client";

/**
 * True while the user has no targets, which is the only state that keeps them
 * out of the app.
 *
 * **Onboarding is a hard gate.** Ruled 30 Aug 2026, reversing the 20 Aug
 * sequencing that put the first meal before the questions. There is no skip and
 * no *Not now*, so this is a fact about the user's data rather than a record of
 * anything they chose.
 *
 * `onboarding_completed` is server-derived. It turns true when the user's first
 * target version is written, and `PATCH /api/users/me/` refuses to set it. A
 * client that could assert it could walk past the gate by claiming to have
 * finished.
 */
export const needsOnboarding = (user: User): boolean => !user.onboarding_completed;
