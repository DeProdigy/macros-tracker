/**
 * The guard on every signed-in route.
 *
 * One redirect here rather than a check inside each screen. When the global 401
 * handler gives up mid-session, it moves the session state and this layout
 * unmounts whatever was on screen — including screens written months from now
 * that never thought about auth. A per-screen check is the version that gets
 * forgotten exactly once and leaves a signed-out user staring at stale data.
 */

import { Redirect, Stack } from "expo-router";

import { needsOnboarding } from "@/lib/onboarding";
import { useSession } from "@/lib/session";

export default function AppLayout() {
  const session = useSession();

  // Only reachable on a deep link into a signed-in route before the launch gate
  // has resolved. Rendering nothing beats guessing and then correcting.
  if (session.status === "loading") {
    return null;
  }

  if (session.status === "signedOut") {
    return <Redirect href="/login" />;
  }

  // The same argument as the auth check above, for the gate that has no
  // targets yet. The launch gate at `/` sends a user here, and a deep link
  // straight to `/today` never passes through it, so before this the gate was
  // advice rather than a rule. Onboarding is a hard gate as of 30 Aug 2026, and
  // a gate with a way round it is not one.
  if (needsOnboarding(session.user)) {
    return <Redirect href="/onboarding" />;
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}
