import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";

import { queryClient } from "@/lib/query-client";
import { SessionProvider } from "@/lib/session";

// Hold the splash open past the first render. Without this, the app paints the
// gate at index.tsx while the session is still `loading`, and a returning user
// sees a blank frame where their app should be. The gate calls hideAsync once
// it knows where to send them.
//
// The promise is deliberately unawaited and its rejection swallowed: this races
// against Expo's own auto-hide, and losing that race is not an error worth
// crashing a launch over.
void SplashScreen.preventAutoHideAsync().catch(() => {});

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <Stack screenOptions={{ headerShown: false }} />
        <StatusBar style="auto" />
      </SessionProvider>
    </QueryClientProvider>
  );
}
