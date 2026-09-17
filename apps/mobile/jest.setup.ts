/**
 * Mock the safe-area library for every suite.
 *
 * `useSafeAreaInsets` throws without a `SafeAreaProvider` above it, and the
 * real provider measures a layout that a test renderer never performs. As of
 * MAC-61 every screen renders inside `components/ui/screen.tsx`, which reads
 * the insets, so without this each of the 18 screen suites would need its own
 * provider.
 *
 * This is the library's own `jest/mock` with one change. Its defaults are
 * zeroes, and zero insets are the one device this app will never run on: a
 * screen that ignores the notch would pass. `TEST_INSETS` is an iPhone 15.
 *
 * A provider still wins when a test supplies one, so `renderWithProviders` and
 * any test that wants different insets keep working.
 *
 * Every binding the factory uses is required inside it. Jest hoists
 * `jest.mock` above the imports, so a factory that closes over anything at
 * module level throws "not allowed to reference any out-of-scope variables". The
 * check is strict enough to reject a type alias, so the props type is inline.
 */

import { jest } from "@jest/globals";

jest.mock("react-native-safe-area-context", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const actual = jest.requireActual<typeof import("react-native-safe-area-context")>(
    "react-native-safe-area-context",
  );
  const { TEST_FRAME, TEST_INSETS } =
    jest.requireActual<typeof import("./test-utils/insets")>("./test-utils/insets");

  return {
    ...actual,
    initialWindowMetrics: { frame: TEST_FRAME, insets: TEST_INSETS },
    useSafeAreaInsets: () => React.useContext(actual.SafeAreaInsetsContext) ?? TEST_INSETS,
    useSafeAreaFrame: () => React.useContext(actual.SafeAreaFrameContext) ?? TEST_FRAME,
    SafeAreaProvider: ({
      children,
      initialMetrics,
    }: {
      children: React.ReactNode;
      initialMetrics?: { frame: typeof TEST_FRAME; insets: typeof TEST_INSETS };
    }) =>
      React.createElement(
        actual.SafeAreaFrameContext.Provider,
        { value: initialMetrics?.frame ?? TEST_FRAME },
        React.createElement(
          actual.SafeAreaInsetsContext.Provider,
          { value: initialMetrics?.insets ?? TEST_INSETS },
          children,
        ),
      ),
  };
});
