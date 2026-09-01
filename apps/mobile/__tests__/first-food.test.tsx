import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { render, screen } from "@testing-library/react-native";

import FirstFoodPrompt from "../app/first-food";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  return { Redirect: ({ href }: { href: string }) => <Text>redirect:{href}</Text> };
});

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSession.mockReturnValue({
    status: "signedIn",
    user: { onboarding_completed: true },
  } as unknown as ReturnType<typeof useSession>);
});

describe("first-food prompt", () => {
  it("confirms saved targets and enables food logging", () => {
    render(<FirstFoodPrompt />);

    expect(screen.getByText("TARGETS SAVED")).toBeTruthy();
    expect(screen.getByRole("button", { name: "LOG YOUR FIRST FOOD" })).toBeEnabled();
  });

  it("does not let an incomplete account bypass onboarding", () => {
    mockUseSession.mockReturnValue({
      status: "signedIn",
      user: { onboarding_completed: false },
    } as unknown as ReturnType<typeof useSession>);

    render(<FirstFoodPrompt />);
    expect(screen.getByText("redirect:/onboarding")).toBeTruthy();
  });
});
