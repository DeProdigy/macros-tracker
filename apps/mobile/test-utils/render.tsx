/**
 * Test helpers for rendering screens.
 *
 * Not under `__tests__/` on purpose: Jest treats every file in that directory
 * as a suite and fails one containing no tests.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react-native";
import type { ReactElement, ReactNode } from "react";

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
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

/**
 * Renders `ui` inside the providers the real app mounts at its root layout.
 *
 * Any screen calling a generated hook needs a QueryClientProvider ancestor —
 * without one React Query throws "No QueryClient set". Screens acquire that
 * dependency invisibly, just by importing a hook, so wrapping here keeps the
 * requirement in one place instead of in every future screen test.
 */
export const renderWithProviders = (ui: ReactElement) => {
  const queryClient = createTestQueryClient();

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return { queryClient, ...render(ui, { wrapper }) };
};
