import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, createTarget, createTargetProposal, getCurrentUser } from "@macros/api-client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import Onboarding from "../app/onboarding";
import { useSession } from "../lib/session";

const mockPush = jest.fn();
const mockReplace = jest.fn();

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    Redirect: ({ href }: { href: string }) => <Text>redirect:{href}</Text>,
    useRouter: () => ({ push: mockPush, replace: mockReplace }),
  };
});

jest.mock("@macros/api-client", () => {
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
    ActivityEnum: {
      sedentary: "sedentary",
      light: "light",
      moderate: "moderate",
      very_active: "very_active",
    },
    ApiError: FakeApiError,
    GoalEnum: { cut: "cut", maintain: "maintain", gain: "gain" },
    TargetProposalRequestSexEnum: { female: "female", male: "male" },
    createTarget: jest.fn(),
    createTargetProposal: jest.fn(),
    getCurrentUser: jest.fn(),
  };
});

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockProposal = createTargetProposal as jest.MockedFunction<typeof createTargetProposal>;
const mockCreate = createTarget as jest.MockedFunction<typeof createTarget>;
const mockMe = getCurrentUser as jest.MockedFunction<typeof getCurrentUser>;
const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockSignOut = jest.fn<() => Promise<void>>();
const mockUpdateUser = jest.fn();
const onboardedUser = { onboarding_completed: true };

beforeEach(() => {
  jest.clearAllMocks();
  mockSignOut.mockResolvedValue(undefined);
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user: { onboarding_completed: false },
    signOut: mockSignOut,
    updateUser: mockUpdateUser,
  } as unknown as ReturnType<typeof useSession>);
  mockProposal.mockResolvedValue({
    status: 200,
    data: {
      targets: { calories: 2150, protein_g: 180, fiber_g: 33 },
      baseline: { calories: 2150, protein_g: 180, fiber_g: 33 },
      clamped: false,
      rationale: "A deterministic explanation.",
    },
  } as never);
  mockCreate.mockResolvedValue({ status: 201, data: {} } as never);
  mockMe.mockResolvedValue({ status: 200, data: onboardedUser } as never);
});

const answerAllQuestions = () => {
  fireEvent.changeText(screen.getByLabelText("Age in years"), "34");
  fireEvent.press(screen.getByText("NEXT"));
  fireEvent.press(screen.getByText("Male"));
  fireEvent.press(screen.getByText("NEXT"));
  fireEvent.changeText(screen.getByLabelText("Height feet"), "5");
  fireEvent.changeText(screen.getByLabelText("Height inches"), "11");
  fireEvent.press(screen.getByText("NEXT"));
  fireEvent.changeText(screen.getByLabelText("Weight in pounds"), "185");
  fireEvent.press(screen.getByText("NEXT"));
  fireEvent.press(screen.getByText("Lose weight"));
  fireEvent.press(screen.getByText("NEXT"));
  fireEvent.press(screen.getByText("Active most days"));
};

describe("mandatory onboarding", () => {
  it("starts at question one with no skip or back action", () => {
    render(<Onboarding />);
    expect(screen.getByText("How old are you?")).toBeTruthy();
    expect(screen.queryByText("BACK")).toBeNull();
    expect(screen.queryByText(/not now/i)).toBeNull();
  });

  it("validates before advancing", () => {
    render(<Onboarding />);
    fireEvent.changeText(screen.getByLabelText("Age in years"), "12");
    fireEvent.press(screen.getByText("NEXT"));
    expect(screen.getByText("Enter an age from 13 to 100.")).toBeTruthy();
    expect(screen.getByText("How old are you?")).toBeTruthy();
  });

  it("preserves answers while moving backward and forward", () => {
    render(<Onboarding />);
    fireEvent.changeText(screen.getByLabelText("Age in years"), "34");
    fireEvent.press(screen.getByText("NEXT"));
    fireEvent.press(screen.getByText("BACK"));
    expect(screen.getByDisplayValue("34")).toBeTruthy();
  });

  it("submits US-unit answers and renders the proposal", async () => {
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));

    await waitFor(() =>
      expect(mockProposal).toHaveBeenCalledWith({
        age: 34,
        sex: "male",
        height_in: 71,
        weight_lb: "185.00",
        goal: "cut",
        activity: "moderate",
      }),
    );
    expect(await screen.findByLabelText("CALORIES 2150 KCAL")).toBeTruthy();
    expect(screen.getByText("A deterministic explanation.")).toBeTruthy();
  });

  it("accepts the proposal, refreshes the session, and replaces onboarding", async () => {
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    await screen.findByText("ACCEPT AND CONTINUE");

    fireEvent.press(screen.getByText("ACCEPT AND CONTINUE"));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith({
        calories: 2150,
        protein_g: 180,
        fiber_g: 33,
        effective_from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }),
    );
    expect(mockMe).toHaveBeenCalled();
    expect(mockReplace).toHaveBeenCalledWith("/first-food");
    expect(mockUpdateUser).toHaveBeenCalledWith(onboardedUser);
  });

  it("carries the proposal into adjustment without saving", async () => {
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    await screen.findByText("ADJUST FIRST");

    fireEvent.press(screen.getByText("ADJUST FIRST"));

    expect(mockPush).toHaveBeenCalledWith({
      pathname: "/targets",
      params: { source: "onboarding", calories: "2150", protein_g: "180", fiber_g: "33" },
    });
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("keeps the proposal when saving is refused and allows retry", async () => {
    mockCreate
      .mockRejectedValueOnce(new ApiError(400, {}))
      .mockResolvedValueOnce({ status: 201, data: {} } as never);
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    await screen.findByText("ACCEPT AND CONTINUE");

    fireEvent.press(screen.getByText("ACCEPT AND CONTINUE"));
    expect(await screen.findByText(/targets were refused/)).toBeTruthy();
    expect(screen.getByLabelText("CALORIES 2150 KCAL")).toBeTruthy();

    fireEvent.press(screen.getByText("ACCEPT AND CONTINUE"));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(2));
    expect(mockReplace).toHaveBeenCalledWith("/first-food");
  });

  it("locks every result action after the target saved but session refresh failed", async () => {
    mockMe.mockRejectedValue(new Error("timeout"));
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    await screen.findByText("ACCEPT AND CONTINUE");

    fireEvent.press(screen.getByText("ACCEPT AND CONTINUE"));
    expect(await screen.findByText(/targets are saved/)).toBeTruthy();

    const accept = screen.getByRole("button", { name: "ACCEPT AND CONTINUE" });
    expect(accept).toBeDisabled();
    expect(screen.getByRole("button", { name: "ADJUST FIRST" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "BACK TO ANSWERS" })).toBeDisabled();
    fireEvent.press(accept);
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });

  it("prevents a second accept before React can render the disabled state", async () => {
    let finishCreate: (value: unknown) => void = () => {};
    mockCreate.mockReturnValue(
      new Promise((resolve) => {
        finishCreate = resolve;
      }) as never,
    );
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    await screen.findByText("ACCEPT AND CONTINUE");

    const accept = screen.getByText("ACCEPT AND CONTINUE");
    fireEvent.press(accept);
    fireEvent.press(accept);
    expect(mockCreate).toHaveBeenCalledTimes(1);

    finishCreate({ status: 201, data: {} });
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/first-food"));
  });

  it("keeps every answer when the request fails and allows retry", async () => {
    mockProposal.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      status: 200,
      data: {
        targets: { calories: 2150, protein_g: 180, fiber_g: 33 },
        baseline: { calories: 2150, protein_g: 180, fiber_g: 33 },
        clamped: false,
        rationale: "A deterministic explanation.",
      },
    } as never);

    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    expect(await screen.findByText(/answers are still here/)).toBeTruthy();

    fireEvent.press(screen.getByText("BACK"));
    fireEvent.press(screen.getByText("BACK"));
    expect(screen.getByDisplayValue("185")).toBeTruthy();
    fireEvent.press(screen.getByText("NEXT"));
    fireEvent.press(screen.getByText("NEXT"));
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    expect(await screen.findByLabelText("CALORIES 2150 KCAL")).toBeTruthy();
  });

  it("does not let Back change answers while the proposal request is in flight", async () => {
    mockProposal.mockReturnValue(new Promise(() => {}) as never);
    render(<Onboarding />);
    answerAllQuestions();

    fireEvent.press(screen.getByText("BUILD MY TARGETS"));

    expect(screen.getByRole("button", { name: "BACK" })).toBeDisabled();
    expect(screen.getByText("How active is your day?")).toBeTruthy();
  });

  it("distinguishes a server refusal from a network failure", async () => {
    mockProposal.mockRejectedValue(new ApiError(400, {}));
    render(<Onboarding />);
    answerAllQuestions();
    fireEvent.press(screen.getByText("BUILD MY TARGETS"));
    expect(await screen.findByText(/answers was refused/)).toBeTruthy();
  });

  it("retains the account escape at the hard gate", async () => {
    render(<Onboarding />);
    fireEvent.press(screen.getByText("SIGN OUT"));
    await waitFor(() => expect(mockSignOut).toHaveBeenCalled());
  });

  it("restores the sign-out action when local sign-out fails", async () => {
    mockSignOut.mockRejectedValue(new Error("storage locked"));
    render(<Onboarding />);
    fireEvent.press(screen.getByText("SIGN OUT"));
    expect(await screen.findByText("SIGN OUT")).toBeTruthy();
  });

  it("redirects a user who already completed onboarding", () => {
    mockUseSession.mockReturnValue({
      status: "signedIn",
      user: { onboarding_completed: true },
      signOut: mockSignOut,
    } as unknown as ReturnType<typeof useSession>);
    render(<Onboarding />);
    expect(screen.getByText("redirect:/today")).toBeTruthy();
  });
});
