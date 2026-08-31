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

import OnboardingPlaceholder from "../app/onboarding";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => ({ Redirect: jest.fn() }));
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
  it("offers no way into the app", () => {
    // The hard gate, at the screen that enforces it. A *Not now* here would
    // undo the 30 Aug 2026 decision by accident.
    render(<OnboardingPlaceholder />);

    expect(screen.queryByText("Not now")).toBeNull();
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
