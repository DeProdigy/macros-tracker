/**
 * The launch gate — three outcomes, and the splash that hides them.
 *
 * `Redirect` is stubbed with a component that renders its href, so each case
 * asserts on where the gate decided to send someone rather than on expo-router
 * internals. The splash calls are spied because "no flash of the wrong screen"
 * is a claim about ordering, and ordering is the only thing that can be checked
 * without a device.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import type { User } from "@macros/api-client";
import { render, screen, waitFor } from "@testing-library/react-native";
import * as SplashScreen from "expo-splash-screen";
import { Text } from "react-native";

import LaunchGate from "../app/index";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => ({
  Redirect: jest.fn(),
}));

jest.mock("expo-splash-screen", () => ({
  preventAutoHideAsync: jest.fn(),
  hideAsync: jest.fn(),
}));

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const { Redirect } = jest.requireMock<typeof import("expo-router")>("expo-router");
const mockRedirect = Redirect as unknown as jest.Mock<
  (props: { href: string }) => React.ReactElement
>;
const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockHideAsync = SplashScreen.hideAsync as jest.MockedFunction<typeof SplashScreen.hideAsync>;

type Session = ReturnType<typeof useSession>;

const sessionOf = (partial: Partial<Session>): Session => partial as Session;

beforeEach(() => {
  jest.clearAllMocks();
  mockHideAsync.mockResolvedValue(undefined);
  mockRedirect.mockImplementation(({ href }) => <Text>redirect:{href}</Text>);
});

describe("LaunchGate", () => {
  it("renders nothing and keeps the splash up while the session loads", () => {
    mockUseSession.mockReturnValue(sessionOf({ status: "loading" }));

    render(<LaunchGate />);

    expect(mockRedirect).not.toHaveBeenCalled();
    // Hiding here is what produces a flash of Welcome for a returning user.
    expect(mockHideAsync).not.toHaveBeenCalled();
  });

  it("sends a signed-out launch to Welcome", async () => {
    mockUseSession.mockReturnValue(sessionOf({ status: "signedOut" }));

    render(<LaunchGate />);

    expect(screen.getByText("redirect:/login")).toBeTruthy();
    await waitFor(() => expect(mockHideAsync).toHaveBeenCalled());
  });

  it("sends a signed-in user with no onboarding toward onboarding", async () => {
    // The third outcome. A user with entries and no targets is a coherent
    // state since doc 26 made the onboarding stack exitable, so "signed in"
    // and "ready for Today" are separate questions.
    mockUseSession.mockReturnValue(
      sessionOf({
        status: "signedIn",
        user: { onboarding_completed: false } as User,
      }),
    );

    render(<LaunchGate />);

    expect(screen.getByText("redirect:/onboarding")).toBeTruthy();
    await waitFor(() => expect(mockHideAsync).toHaveBeenCalled());
  });

  it("sends a fully onboarded user to Today", async () => {
    mockUseSession.mockReturnValue(
      sessionOf({
        status: "signedIn",
        user: { onboarding_completed: true } as User,
      }),
    );

    render(<LaunchGate />);

    expect(screen.getByText("redirect:/today")).toBeTruthy();
    await waitFor(() => expect(mockHideAsync).toHaveBeenCalled());
  });
});
