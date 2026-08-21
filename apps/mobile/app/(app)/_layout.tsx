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

  return <Stack screenOptions={{ headerShown: false }} />;
}
