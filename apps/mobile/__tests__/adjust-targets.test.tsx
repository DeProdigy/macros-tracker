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
import { localIsoDate } from "../lib/target-save";

const mockReplace = jest.fn();
const mockBack = jest.fn();
const mockCanGoBack = jest.fn<() => boolean>();
const mockParams = jest.fn<() => Record<string, string>>();

jest.mock("expo-router", () => ({
  Redirect: jest.fn(),
  useLocalSearchParams: () => mockParams(),
  useRouter: () => ({ replace: mockReplace, back: mockBack, canGoBack: mockCanGoBack }),
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

/** The session as it is *before* the save, which is what decides the destination. */
const signedInAs = (user: { onboarding_completed: boolean }) =>
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user,
    updateUser: mockUpdateUser,
  } as unknown as ReturnType<typeof useSession>);

beforeEach(() => {
  jest.clearAllMocks();
  // Default: someone editing from Settings, who already owns targets.
  signedInAs({ onboarding_completed: true });
  mockCanGoBack.mockReturnValue(false);
  mockParams.mockReturnValue({});
  mockCurrent.mockRejectedValue(new ApiError(404, null));
  mockCreate.mockResolvedValue({ status: 201, data: {} } as never);
  mockMe.mockResolvedValue({ status: 200, data: onboardedUser } as never);
});

const renderScreen = async () => {
  render(<AdjustTargets />);
  // The seed request resolves before the form renders.
  await waitFor(() => expect(screen.getByRole("button", { name: /SAVE/ })).toBeTruthy());
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

  it("prevents a second save before React can render the disabled state", async () => {
    let finishCreate: (value: unknown) => void = () => {};
    mockCreate.mockReturnValue(
      new Promise((resolve) => {
        finishCreate = resolve;
      }) as never,
    );
    await renderScreen();

    const save = screen.getByText("SAVE NEW VERSION");
    fireEvent.press(save);
    fireEvent.press(save);
    expect(mockCreate).toHaveBeenCalledTimes(1);

    finishCreate({ status: 201, data: {} });
    await waitFor(() => expect(mockMe).toHaveBeenCalled());
  });
});

describe("failures the first version hid", () => {
  it("does not paint the starting point while the seed is still in flight", async () => {
    // The double-run this guards. `session.status` is a dependency, so a cold
    // start runs the effect once while the session is loading and again once it
    // resolves. Clearing the loading flag on that first pass painted 2,000 over
    // a user whose real targets were still arriving, and a step taken in that
    // window was overwritten when they landed.
    mockUseSession.mockReturnValue({ status: "loading" } as unknown as ReturnType<
      typeof useSession
    >);

    let landSeed: (value: unknown) => void = () => {};
    mockCurrent.mockReturnValue(
      new Promise((resolve) => {
        landSeed = resolve;
      }) as never,
    );

    const { rerender } = render(<AdjustTargets />);

    signedInAs({ onboarding_completed: true });
    rerender(<AdjustTargets />);

    expect(screen.queryByText("2000 kcal")).toBeNull();

    landSeed({ status: 200, data: { calories: 2400, protein_g: 180, fiber_g: 40 } });
    await waitFor(() => expect(screen.getByText("2400 kcal")).toBeTruthy());
  });

  it("says so when the current targets could not be loaded", async () => {
    // Not a 404. A user whose targets are 2,400 opens this on a dropped
    // connection, sees 2,000, and saves a number they never chose.
    mockCurrent.mockRejectedValue(new ApiError(500, null));

    await renderScreen();

    expect(screen.getByText(/did not load/)).toBeTruthy();
    expect(screen.getByText("2000 kcal")).toBeTruthy();
  });

  it("does not claim nothing was saved when only the refetch failed", async () => {
    // The 201 already happened. The row exists and onboarding is already
    // complete, so "Nothing changed" would send the user back to save a
    // duplicate version for the same date.
    mockMe.mockRejectedValue(new Error("timeout"));

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(screen.getByText(/are saved/)).toBeTruthy());
    expect(screen.queryByText(/weren't saved/)).toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("shows a refusal the steppers cannot fix", async () => {
    // `validate_effective_from` rejects a device clock more than a day out, in
    // the same body shape. Reading only the three stepper keys turned a real
    // reason into "the reason did not come through".
    mockCreate.mockRejectedValue(
      new ApiError(400, { effective_from: ["Must be within a day of the current date."] }),
    );

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(screen.getByText(/within a day/)).toBeTruthy());
  });

  it("returns to Settings when that is where the user came from", async () => {
    // From onboarding there is no Settings to go back to, so that path still
    // replaces to Today. From Settings, landing on Today is a surprise.
    mockCanGoBack.mockReturnValue(true);

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(mockBack).toHaveBeenCalled());
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("seeds onboarding adjustment from the proposal without loading current targets", async () => {
    signedInAs({ onboarding_completed: false });
    mockParams.mockReturnValue({
      source: "onboarding",
      calories: "2150",
      protein_g: "180",
      fiber_g: "33",
    });

    await renderScreen();

    expect(screen.getByText("2150 kcal")).toBeTruthy();
    expect(screen.getByText("180 g")).toBeTruthy();
    expect(screen.getByText("33 g")).toBeTruthy();
    expect(screen.getByText("SAVE AND CONTINUE")).toBeTruthy();
    expect(screen.getByText(/first daily targets/)).toBeTruthy();
    expect(screen.queryByText(/last week's progress/)).toBeNull();
    expect(mockCurrent).not.toHaveBeenCalled();
  });

  it("normalizes proposal route values to the stepper bounds and whole numbers", async () => {
    signedInAs({ onboarding_completed: false });
    mockParams.mockReturnValue({
      source: "onboarding",
      calories: "9999",
      protein_g: "185.6",
      fiber_g: "101",
    });

    await renderScreen();

    expect(screen.getByText("5000 kcal")).toBeTruthy();
    expect(screen.getByText("186 g")).toBeTruthy();
    expect(screen.getByText("100 g")).toBeTruthy();
  });

  it("keeps saving locked after the row was saved but session refresh failed", async () => {
    mockMe.mockRejectedValue(new Error("timeout"));
    await renderScreen();

    fireEvent.press(screen.getByText("SAVE NEW VERSION"));
    expect(await screen.findByText(/are saved/)).toBeTruthy();
    const saveButton = screen.getByRole("button", { name: "SAVE NEW VERSION" });
    expect(saveButton).toBeDisabled();

    fireEvent.press(saveButton);
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });

  it("sends a user finishing onboarding to the first-food prompt, even if it can go back", async () => {
    // The bug the first version of this fix shipped, and the reason this test
    // sets `canGoBack` to **true**.
    //
    // `app/index.tsx` redirects to `/onboarding`, which replaces, and
    // `onboarding.tsx` renders a `Link` to `/targets`, which pushes. So the
    // real onboarding stack is `[/onboarding, /targets]` and `canGoBack()` is
    // true. Keying off history alone sent a user who had just set their first
    // target straight back to "Set your targets".
    //
    // The previous version of this test stubbed `canGoBack` false, which is a
    // state the onboarding path never reaches. It asserted the right
    // destination from the wrong premise, so it would have passed over the bug.
    mockCanGoBack.mockReturnValue(true);
    signedInAs({ onboarding_completed: false });

    await renderScreen();
    fireEvent.press(screen.getByText("SAVE NEW VERSION"));

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/first-food"));
    expect(mockBack).not.toHaveBeenCalled();
  });
});

describe("localIsoDate", () => {
  it("reads the phone's local date, not UTC", () => {
    // Asserted against a stub rather than a real `Date`, because CI runs in UTC
    // where local and UTC agree and the bug is invisible. The stub's local
    // getters say 31 Aug while its UTC form says 30 Aug, which is exactly what
    // an Auckland morning looks like.
    //
    // `toISOString().slice(0, 10)` is the wrong answer this guards against. It
    // converts to UTC first, so someone setting targets at 09:00 in Auckland
    // files them under yesterday.
    const aucklandMorning = {
      getFullYear: () => 2026,
      getMonth: () => 7,
      getDate: () => 31,
      toISOString: () => "2026-08-30T21:00:00.000Z",
    } as unknown as Date;

    expect(localIsoDate(aucklandMorning)).toBe("2026-08-31");
  });

  it("pads a single-digit month and day", () => {
    const newYearsDay = {
      getFullYear: () => 2027,
      getMonth: () => 0,
      getDate: () => 1,
    } as unknown as Date;

    expect(localIsoDate(newYearsDay)).toBe("2027-01-01");
  });
});
