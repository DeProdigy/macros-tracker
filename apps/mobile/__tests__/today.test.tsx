/**
 * The Today shell.
 *
 * Thin on purpose, and the tests are thin to match. The one thing worth
 * asserting is that it renders the identity the server returned, because that
 * is E2's whole claim: the token in the Keychain still buys an authenticated
 * request.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import type { User } from "@macros/api-client";
import { render, screen } from "@testing-library/react-native";

import TodayScreen from "../app/(app)/today";
import { useSession } from "../lib/session";

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");

  return { Link: ({ children }: { children: React.ReactNode }) => <Text>{children}</Text> };
});

jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;

type Session = ReturnType<typeof useSession>;

const signedInAs = (user: Partial<User>) =>
  mockUseSession.mockReturnValue({ status: "signedIn", user } as unknown as Session);

beforeEach(() => {
  jest.clearAllMocks();
});

describe("TodayScreen", () => {
  it("names the signed-in user", () => {
    signedInAs({ name: "Alex", email: "alex@example.com" });

    render(<TodayScreen />);

    expect(screen.getByText(/signed in as alex/i)).toBeTruthy();
  });

  it("falls back to the email when Apple never supplied a name", () => {
    // `name` is an empty string rather than null when Apple withheld it on the
    // first authorization, and it can never be recovered for that user.
    signedInAs({ name: "", email: "alex@example.com" });

    render(<TodayScreen />);

    expect(screen.getByText(/signed in as alex@example.com/i)).toBeTruthy();
  });

  it("says logging is not built yet instead of drawing empty rings", () => {
    signedInAs({ name: "Alex", email: null });

    render(<TodayScreen />);

    expect(screen.getByText("Nothing logged yet")).toBeTruthy();
    expect(screen.getByText(/E4/)).toBeTruthy();
  });

  it("offers a route to Settings", () => {
    signedInAs({ name: "Alex", email: null });

    render(<TodayScreen />);

    expect(screen.getByText("Settings")).toBeTruthy();
  });
});
