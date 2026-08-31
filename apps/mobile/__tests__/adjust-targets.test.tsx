/**
 * The manual target editor, and the two things about it that are not obvious.
 *
 * The first is the round trip. Saving a first target flips
 * `onboarding_completed` on the server, and the route guard reads the session
 * rather than the network. Skip the refetch and the user saves targets and
 * stays on this screen, which is the same class of bug MAC-47 fixed.
 *
 * The second is the 400. `reject_outside_absolute` reports every failing field
 * at once, and a screen that shows one of them makes the user guess twice.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, createTarget, getCurrentTarget, getCurrentUser } from "@macros/api-client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import AdjustTargets from "../app/targets";
import { useSession } from "../lib/session";

const mockReplace = jest.fn();

jest.mock("expo-router", () => ({
  Redirect: jest.fn(),
  useRouter: () => ({ replace: mockReplace }),
}));

jest.mock("@macros/api-client", () => {
  // Written out longhand rather than with TypeScript parameter properties.
  // Babel's `jest.mock` scope check rejects those inside a module factory,
  // reading the shorthand as an out-of-scope reference.
  class FakeApiError extends Error {
    status: number;
    body: unknown;

    constructor(status: number, body: unknown) {
      super("failed");
      this.status = status;
      this.body = body;
    }
  }

  return {
    ApiError: FakeApiError,
    createTarget: jest.fn(),
    getCurrentTarget: jest.fn(),
    getCurrentUser: jest.fn(),
  };
});

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockCreate = createTarget as jest.MockedFunction<typeof createTarget>;
const mockCurrent = getCurrentTarget as jest.MockedFunction<typeof getCurrentTarget>;
const mockMe = getCurrentUser as jest.MockedFunction<typeof getCurrentUser>;
const mockUpdateUser = jest.fn();

const onboardedUser = { onboarding_completed: true };

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user: {},
    updateUser: mockUpdateUser,
  } as unknown as ReturnType<typeof useSession>);
  mockCurrent.mockRejectedValue(new Error("404"));
  mockCreate.mockResolvedValue({ status: 201, data: {} } as never);
  mockMe.mockResolvedValue({ status: 200, data: onboardedUser } as never);
});

const renderScreen = async () => {
  render(<AdjustTargets />);
  // The seed request resolves before the form renders.
  await waitFor(() => expect(screen.getByText("Your call")).toBeTruthy());
};

describe("the manual target editor", () => {
  it("starts a first-time user on the neutral values", async () => {
    // A 404 from `current/` is the ordinary first-run answer, not a failure,
    // and must not surface as an error.
    await renderScreen();

    // Queried with the unit, because the value and unit are one composite Text
    // so a screen reader says "2000 kcal" rather than two orphaned numbers.
    expect(screen.getByText("2000 kcal")).toBeTruthy();
    expect(screen.getByText("140 g")).toBeTruthy();
    expect(screen.getByText("30 g")).toBeTruthy();
  });

  it("seeds from the current version when one exists", async () => {
    mockCurrent.mockResolvedValue({
      status: 200,
      data: { calories: 2150, protein_g: 175, fiber_g: 34 },
    } as never);

    await renderScreen();

    expect(screen.getByText("2150 kcal")).toBeTruthy();
  });

  it("steps calories by ten", async () => {
    await renderScreen();

    fireEvent.press(screen.getByLabelText("Increase calories"));

    expect(screen.getByText("2010 kcal")).toBeTruthy();
  });

  it("refetches the user after saving, so the route guard lets them in", async () => {
    // The round trip MAC-47 exists for, at the screen that completes it.
    await renderScreen();

    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledWith(onboardedUser));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/today"));
  });

  it("shows every field the server refused, not the first", async () => {
    mockCreate.mockRejectedValue(
      new ApiError(400, {
        calories: ["Must be between 1000 and 5000. Received 400."],
        fiber_g: ["Must be between 0 and 100. Received 500."],
      }),
    );

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(screen.getByText(/between 1000 and 5000/)).toBeTruthy());
    expect(screen.getByText(/between 0 and 100/)).toBeTruthy();
    // Still on the screen, with the numbers they typed.
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("says something when a refusal arrives with no readable reason", async () => {
    // The 400 body is typed `void` in the generated client, so the shape is not
    // guaranteed. Rendering `undefined` at a user is the failure to avoid.
    mockCreate.mockRejectedValue(new ApiError(400, "nope"));

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(screen.getByText(/refused/)).toBeTruthy());
  });

  it("keeps the user on the screen when the network fails", async () => {
    mockCreate.mockRejectedValue(new Error("offline"));

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(screen.getByText(/weren't saved/)).toBeTruthy());
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
