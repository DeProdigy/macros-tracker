/**
 * The guard on every signed-in route.
 *
 * The onboarding case is the reason this file exists. The launch gate at `/`
 * checked it, and a deep link straight to `/today` never runs the launch gate,
 * so a user with no targets walked in. That made the gate advice rather than a
 * rule, and onboarding became a hard gate on 30 Aug 2026.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import type { User } from "@macros/api-client";
import { render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import AppLayout from "../app/(app)/_layout";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => ({
  Redirect: jest.fn(),
  Stack: jest.fn(),
}));

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const { Redirect, Stack } = jest.requireMock<typeof import("expo-router")>("expo-router");
const mockRedirect = Redirect as unknown as jest.Mock<
  (props: { href: string }) => React.ReactElement
>;
const mockStack = Stack as unknown as jest.Mock<() => React.ReactElement>;
const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

type Session = ReturnType<typeof useSession>;
const sessionOf = (partial: Partial<Session>): Session => partial as Session;

beforeEach(() => {
  jest.clearAllMocks();
  mockRedirect.mockImplementation(({ href }) => <Text>redirect:{href}</Text>);
  mockStack.mockImplementation(() => <Text>stack</Text>);
});

describe("AppLayout", () => {
  it("renders nothing while the session loads", () => {
    mockUseSession.mockReturnValue(sessionOf({ status: "loading" }));

    render(<AppLayout />);

    expect(mockRedirect).not.toHaveBeenCalled();
    expect(mockStack).not.toHaveBeenCalled();
  });

  it("sends a signed-out deep link to Welcome", () => {
    mockUseSession.mockReturnValue(sessionOf({ status: "signedOut" }));

    render(<AppLayout />);

    expect(screen.getByText("redirect:/login")).toBeTruthy();
  });

  it("sends a deep link from a user with no targets back to onboarding", () => {
    // The hole this guard closes. `/today` is reachable by deep link, by a
    // notification tap, and by any `router.replace` written later that forgets
    // to check. A gate with a way round it is not a gate.
    mockUseSession.mockReturnValue(
      sessionOf({ status: "signedIn", user: { onboarding_completed: false } as User }),
    );

    render(<AppLayout />);

    expect(screen.getByText("redirect:/onboarding")).toBeTruthy();
  });

  it("lets an onboarded user through", () => {
    mockUseSession.mockReturnValue(
      sessionOf({ status: "signedIn", user: { onboarding_completed: true } as User }),
    );

    render(<AppLayout />);

    expect(screen.getByText("stack")).toBeTruthy();
    expect(mockRedirect).not.toHaveBeenCalled();
  });
});
