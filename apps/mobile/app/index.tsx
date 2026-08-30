/**
 * The launch gate.
 *
 * Doc 04's flow, in one component:
 *
 *   token in secure store?
 *     no  → Welcome
 *     yes → valid? → needs onboarding?
 *                      yes → onboarding
 *                      no  → Today
 *
 * Three outcomes, not two. A user with entries and no targets is a coherent
 * state now that doc 26 made the onboarding stack exitable, so "signed in" and
 * "ready for Today" are different questions.
 *
 * `needsOnboarding` owns the third question, and it reads two fields rather
 * than one. See `lib/onboarding.ts` for why a skip has to count.
 *
 * `SessionProvider` did the asking. This route only reads the answer and
 * redirects, which is what routing-from-state buys: nothing here has to know
 * how a session is restored, and the same three lines keep working when the
 * global 401 handler flips the session out from under a screen.
 */

import { Redirect } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";

import { needsOnboarding } from "@/lib/onboarding";
import { useSession } from "@/lib/session";

export default function LaunchGate() {
  const session = useSession();
  const isLoading = session.status === "loading";

  // Hide the splash only once there is somewhere to send them. Hiding earlier
  // shows a flash of the wrong screen, which reads to a returning user as
  // having been logged out.
  useEffect(() => {
    if (!isLoading) {
      void SplashScreen.hideAsync().catch(() => {});
    }
  }, [isLoading]);

  if (isLoading) {
    // The splash is still up, so rendering nothing is rendering the right thing.
    return null;
  }

  if (session.status === "signedOut") {
    return <Redirect href="/login" />;
  }

  // Through the helper, never inline. The rule reads two fields, and the same
  // rule runs in `(auth)/login.tsx`. Two inline copies is how one of them gets
  // updated and the other does not.
  if (needsOnboarding(session.user)) {
    return <Redirect href="/onboarding" />;
  }

  return <Redirect href="/today" />;
}
