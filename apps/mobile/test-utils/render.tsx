/**
 * Test helpers for rendering screens.
 *
 * Not under `__tests__/` on purpose: Jest treats every file in that directory
 * as a suite and fails one containing no tests.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react-native";
import type { ReactElement, ReactNode } from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { TEST_FRAME, TEST_INSETS } from "./insets";

/**
 * A QueryClient scoped to one test.
 *
 * Retries are off: React Query retries failed queries three times with backoff
 * by default, so an error-path test would sit through several seconds of
 * retries before the error state ever renders, and usually time out instead.
 * Each call returns a fresh client so cached data can't leak between tests.
 */
export const createTestQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false, gcTime: Infinity },
    },
  });

/**
 * Renders `ui` inside the providers the real app mounts at its root layout.
 *
 * Any screen calling a generated hook needs a QueryClientProvider ancestor —
 * without one React Query throws "No QueryClient set". Screens acquire that
 * dependency invisibly, just by importing a hook, so wrapping here keeps the
 * requirement in one place instead of in every future screen test.
 *
 * `SafeAreaProvider` is here for the same reason as of MAC-61. Every screen
 * renders inside `components/ui/screen.tsx`, which reads the insets. A suite
 * using plain `render` gets the same numbers from `jest.setup.tsx`, so this
 * wrapper is about mirroring the real root rather than about making the insets
 * available.
 */
export const renderWithProviders = (ui: ReactElement) => {
  const queryClient = createTestQueryClient();

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider initialMetrics={{ insets: TEST_INSETS, frame: TEST_FRAME }}>
        {children}
      </SafeAreaProvider>
    </QueryClientProvider>
  );

  return { queryClient, ...render(ui, { wrapper }) };
};

/**
 * The fake-timer options that freeze `Date` and nothing else.
 *
 * A test that asserts a calendar date has to freeze the clock, because the
 * screens call `new Date()` during render. Faking the timer functions too makes
 * React Native Testing Library hang: React's scheduler and RNTL's own waiting
 * both go through them, so nothing ever advances.
 *
 * Pass as `jest.useFakeTimers({ doNotFake: [...REAL_TIMERS] })`, then
 * `jest.setSystemTime(...)`. Restore with `jest.useRealTimers()` in `afterEach`,
 * or the frozen clock leaks into every later suite in the same worker.
 *
 * Spread at the call site. `as const` keeps the literal types Jest's
 * `FakeableAPI` union needs, and Jest wants a mutable array, so a bare
 * reference fails to typecheck.
 */
export const REAL_TIMERS = [
  "nextTick",
  "setImmediate",
  "setTimeout",
  "setInterval",
  "clearTimeout",
  "clearInterval",
  "performance",
  "queueMicrotask",
  "requestAnimationFrame",
  "cancelAnimationFrame",
] as const;
