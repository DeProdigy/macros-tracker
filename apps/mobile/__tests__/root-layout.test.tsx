/**
 * The font gate at the root.
 *
 * Worth a test because the failure is invisible in code review and obvious on a
 * phone. If the gate lets the first render through, every screen paints in the
 * system font and swaps to Archivo a frame later. Reviewers do not catch that.
 * A cold start does.
 *
 * The error branch matters just as much. A font file that fails to load must
 * not leave the app on a splash screen forever, so the gate opens on an error
 * too and the app runs in the fallback font.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

jest.mock("expo-font", () => ({ useFonts: jest.fn() }));

jest.mock("expo-router", () => ({ Stack: jest.fn() }));

// The real provider renders nothing until it measures a layout, and no layout
// happens in a test renderer. Passing it through keeps this suite about the
// font gate. `ui-primitives.test.tsx` exercises the real provider with fixed
// metrics.
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
  initialWindowMetrics: null,
}));

jest.mock("expo-splash-screen", () => ({
  preventAutoHideAsync: jest.fn(() => Promise.resolve()),
  hideAsync: jest.fn(() => Promise.resolve()),
}));

jest.mock("../lib/session", () => ({
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import { useFonts } from "expo-font";
import { Stack } from "expo-router";

import RootLayout from "../app/_layout";

const mockUseFonts = useFonts as unknown as jest.Mock<() => [boolean, Error | null]>;
const mockStack = Stack as unknown as jest.Mock<() => React.ReactElement>;

beforeEach(() => {
  jest.clearAllMocks();
  mockStack.mockImplementation(() => <Text>stack</Text>);
});

describe("RootLayout", () => {
  it("renders nothing until the fonts load", () => {
    mockUseFonts.mockReturnValue([false, null]);

    render(<RootLayout />);

    expect(mockStack).not.toHaveBeenCalled();
  });

  it("renders once the fonts load", () => {
    mockUseFonts.mockReturnValue([true, null]);

    render(<RootLayout />);

    expect(screen.getByText("stack")).toBeTruthy();
  });

  it("renders anyway when a font fails to load", () => {
    mockUseFonts.mockReturnValue([false, new Error("missing file")]);

    render(<RootLayout />);

    expect(screen.getByText("stack")).toBeTruthy();
  });
});
