import { Stack } from "expo-router";

// Route group `(auth)` — organizes the unauthenticated stack without adding a
// URL segment (so this file lives at /(auth)/ but routes render at /login etc.).
// The auth epic (E2) fills this in.
export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
