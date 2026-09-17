import { QueryClientProvider } from "@tanstack/react-query";
import { useFonts } from "expo-font";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider, initialWindowMetrics } from "react-native-safe-area-context";

import { queryClient } from "@/lib/query-client";
import { SessionProvider } from "@/lib/session";
import { colors, fontAssets } from "@/lib/theme";

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
  // Custom fonts arrive asynchronously, because they are files the bundle has
  // to read. Rendering before they land paints every screen in the system font
  // and then swaps it a frame later. The web calls that a flash of unstyled
  // text, and on a phone it reads as the app stuttering on launch.
  //
  // Returning null here keeps the splash up until the swap can no longer
  // happen. The gate at index.tsx never mounts before that, so it cannot hide
  // the splash early. The two conditions stay independent and neither has to
  // know about the other.
  const [fontsLoaded, fontError] = useFonts(fontAssets);

  // A missing font file is not worth a blank app. The screens still render in
  // the system font, which is ugly and legible, and that beats a launch that
  // never finishes.
  if (!fontsLoaded && !fontError) {
    return null;
  }

  return (
    <QueryClientProvider client={queryClient}>
      {/*
        `initialMetrics` hands the provider the insets the native side already
        knows. Without it the provider measures itself on first layout and
        renders nothing until that lands, which is one blank frame on every
        launch.
      */}
      <SafeAreaProvider initialMetrics={initialWindowMetrics}>
        <SessionProvider>
          <Stack
            screenOptions={{
              // Without this the router paints its own white card behind a
              // screen during a transition, which flashes white on a black app.
              contentStyle: { backgroundColor: colors.background },
              headerShown: false,
            }}
          />
          {/* Dark only as of MAC-61, so the status bar is always light. */}
          <StatusBar style="light" />
        </SessionProvider>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
