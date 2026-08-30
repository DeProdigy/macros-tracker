/**
 * The placeholder's *Not now*, which is a real exit rather than a redirect.
 *
 * Worth testing a screen MAC-42 deletes, because in slice 1 this button is the
 * only route a new user has to Today, and therefore the only route to the
 * Settings row where targets get set. The two cases below are "the skip
 * sticks" and "the skip still lets you out when the network is down".
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { updateCurrentUser } from "@macros/api-client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import OnboardingPlaceholder from "../app/onboarding";
import { useSession } from "../lib/session";

const mockReplace = jest.fn();

jest.mock("expo-router", () => ({
  Redirect: jest.fn(),
  useRouter: () => ({ replace: mockReplace }),
}));

jest.mock("@macros/api-client", () => ({ updateCurrentUser: jest.fn() }));
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockUpdate = updateCurrentUser as jest.MockedFunction<typeof updateCurrentUser>;
const mockUpdateUser = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user: {},
    updateUser: mockUpdateUser,
  } as unknown as ReturnType<typeof useSession>);
});

describe("the Not now button", () => {
  it("records the skip on the server and in the session", async () => {
    const user = { onboarding_completed: false, onboarding_skipped_at: "2026-08-30T12:00:00Z" };
    mockUpdate.mockResolvedValue({ status: 200, data: user } as never);

    render(<OnboardingPlaceholder />);
    fireEvent.press(screen.getByText("Not now"));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalled());
    // The session copy matters as much as the write. The launch gate reads the
    // session, so without this the next cold start uses a stale user and sends
    // them straight back here.
    await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith(user));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/today"));
  });

  it("still lets the user out when the write fails", async () => {
    mockUpdate.mockRejectedValue(new Error("offline"));

    render(<OnboardingPlaceholder />);
    fireEvent.press(screen.getByText("Not now"));

    // The exit is a promise doc 26 makes. Blocking it on a network call traps a
    // user with no signal on the one screen whose point is that you can leave.
    // The cost of failing is that the skip lasts one launch.
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/today"));
    expect(mockUpdateUser).not.toHaveBeenCalled();
  });
});
