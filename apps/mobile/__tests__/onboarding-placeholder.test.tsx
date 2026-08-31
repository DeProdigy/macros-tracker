/**
 * The onboarding placeholder, and the one thing on it that is not a placeholder.
 *
 * The screen is a stand-in that MAC-42 deletes. Its sign-out is not: closing the
 * deep-link hole put `(app)/settings.tsx` behind the gate, and that is where
 * sign-out and account deletion live. Without the button here, a user who signs
 * in and has no targets cannot leave their own account at all.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import type React from "react";

import OnboardingPlaceholder from "../app/onboarding";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    Redirect: ({ href }: { href: string }) => <Text>redirect:{href}</Text>,
    // Rendered as its label so a test can assert on the route it points at.
    Link: ({ href, children }: { href: string; children: React.ReactNode }) => (
      <Text>
        link:{href}:{children}
      </Text>
    ),
  };
});
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockSignOut = jest.fn<() => Promise<void>>();

beforeEach(() => {
  jest.clearAllMocks();
  mockSignOut.mockResolvedValue(undefined);
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user: {},
    signOut: mockSignOut,
  } as unknown as ReturnType<typeof useSession>);
});

describe("the onboarding placeholder", () => {
  it("offers no way around the gate", () => {
    // A *Not now* here would undo the 30 Aug 2026 decision by accident.
    render(<OnboardingPlaceholder />);

    expect(screen.queryByText("Not now")).toBeNull();
  });

  it("offers a way through the gate", () => {
    // MAC-50. Setting a target is what flips `onboarding_completed`, so this
    // link and the six questions end in the same place by the same route.
    render(<OnboardingPlaceholder />);

    expect(screen.getByText(/link:\/targets:/)).toBeTruthy();
  });

  it("still lets the user out of their own account", () => {
    // Not a leftover exit. `(app)/settings.tsx` holds sign-out and account
    // deletion, and the route guard hides that whole group from anyone without
    // targets. In slice 1 that is every user, so without this button the
    // in-app account-deletion path App Review looks for exists for nobody.
    render(<OnboardingPlaceholder />);
    fireEvent.press(screen.getByText("Sign out"));

    return waitFor(() => expect(mockSignOut).toHaveBeenCalled());
  });
});

describe("who may see the placeholder", () => {
  it("sends a user who already has targets to Today", () => {
    // `/targets` sits on top of this screen in the stack, so anything that pops
    // back lands here. Before this guard, a user who had just saved their first
    // target could end up on "Set your targets" with no way out but killing the
    // app, and tapping the button again wrote a second version for the day.
    mockUseSession.mockReturnValue({
      status: "signedIn",
      user: { onboarding_completed: true },
      signOut: mockSignOut,
    } as unknown as ReturnType<typeof useSession>);

    render(<OnboardingPlaceholder />);

    expect(screen.getByText("redirect:/today")).toBeTruthy();
    expect(screen.queryByText("Set your targets")).toBeNull();
  });
});
