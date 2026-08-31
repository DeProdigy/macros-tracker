/**
 * The launch gate.
 *
 * Doc 04's flow, in one component:
 *
 *   token in secure store?
 *     no  → Welcome
 *     yes → valid? → has targets?
 *                      no  → onboarding
 *                      yes → Today
 *
 * Three outcomes, not two. "Signed in" and "ready for Today" are different
 * questions: onboarding is a hard gate, so a signed-in user with no targets
 * belongs on the onboarding screen and nowhere else.
 *
 * `needsOnboarding` owns the third question. See `lib/onboarding.ts`.
 *
 * **This is not the only place that asks it.** A deep link straight to `/today`
 * never runs this route, so `(app)/_layout.tsx` asks the same question for
 * every signed-in screen. Do not treat this file as the enforcement point.
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

  // Through the helper, never inline. The same rule runs in `(auth)/login.tsx`
  // and in `(app)/_layout.tsx`, and it has already changed once: it read two
  // fields while onboarding was skippable. Three inline copies is how one of
  // them gets updated and the others do not.
  if (needsOnboarding(session.user)) {
    return <Redirect href="/onboarding" />;
  }

  return <Redirect href="/today" />;
}
