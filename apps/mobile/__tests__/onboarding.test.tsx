import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, createTargetProposal } from "@macros/api-client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import Onboarding from "../app/onboarding";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  return { Redirect: ({ href }: { href: string }) => <Text>redirect:{href}</Text> };
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
    createTargetProposal: jest.fn(),
  };
});

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockProposal = createTargetProposal as jest.MockedFunction<typeof createTargetProposal>;
const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockSignOut = jest.fn<() => Promise<void>>();

beforeEach(() => {
  jest.clearAllMocks();
  mockSignOut.mockResolvedValue(undefined);
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user: { onboarding_completed: false },
    signOut: mockSignOut,
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
