/**
 * Settings: targets, sign out, and the delete-account confirmation.
 *
 * Both stores require an in-app deletion path, which is why account deletion
 * has a screen this early. The cases below are about what the screen refuses to
 * do: delete without a confirmation, and sign someone out of an account that
 * survived the attempt.
 */

import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, getCurrentTarget, type User } from "@macros/api-client";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import SettingsScreen from "../app/(app)/settings";
import { useSession } from "../lib/session";

let mockFocusCallback: (() => void | (() => void)) | null = null;

jest.mock("expo-router", () => {
  const { Text } = jest.requireActual<typeof import("react-native")>("react-native");
  const React = jest.requireActual<typeof import("react")>("react");

  return {
    useRouter: () => ({ back: jest.fn() }),
    useFocusEffect: (callback: () => void | (() => void)) =>
      React.useEffect(() => {
        mockFocusCallback = callback;
        return callback();
      }, [callback]),
    Link: ({ children }: { children: React.ReactNode }) => <Text>{children}</Text>,
  };
});

jest.mock("@macros/api-client", () => {
  const actual = jest.requireActual<typeof import("@macros/api-client")>("@macros/api-client");
  return { ...actual, getCurrentTarget: jest.fn() };
});
jest.mock("../lib/session", () => ({ useSession: jest.fn() }));

const mockUseSession = useSession as jest.MockedFunction<typeof useSession>;
const mockCurrent = getCurrentTarget as jest.MockedFunction<typeof getCurrentTarget>;

type Session = ReturnType<typeof useSession>;

const signOut = jest.fn<() => Promise<void>>();
const deleteAccount = jest.fn<() => Promise<void>>();

const user = { id: 1, name: "Alex", email: "alex@example.com" } as User;

beforeEach(() => {
  jest.clearAllMocks();
  signOut.mockResolvedValue(undefined);
  deleteAccount.mockResolvedValue(undefined);
  mockCurrent.mockImplementation(() => new Promise(() => {}));
  mockFocusCallback = null;

  mockUseSession.mockReturnValue({
    status: "signedIn",
    user,
    signIn: jest.fn(),
    signOut,
    deleteAccount,
  } as unknown as Session);
});

describe("targets", () => {
  it("shows the current singleton and both target actions", async () => {
    mockCurrent.mockResolvedValue({
      status: 200,
      data: { id: 1, calories: 2150, protein_g: 180, fiber_g: 33 },
    } as Awaited<ReturnType<typeof getCurrentTarget>>);
    render(<SettingsScreen />);

    expect(await screen.findByText("2,150")).toBeTruthy();
    expect(screen.getByText("180")).toBeTruthy();
    expect(screen.getByText("33")).toBeTruthy();
    expect(screen.getByText("Adjust")).toBeTruthy();
    expect(screen.getByText("History")).toBeTruthy();
  });

  it("shows an empty state when no current version exists", async () => {
    mockCurrent.mockRejectedValue(new ApiError(404, null));
    render(<SettingsScreen />);
    expect(await screen.findByText("No targets set.")).toBeTruthy();
  });

  it("retries a failed current-target read", async () => {
    mockCurrent.mockRejectedValueOnce(new ApiError(500, null)).mockResolvedValueOnce({
      status: 200,
      data: { id: 2, calories: 2200, protein_g: 175, fiber_g: 30 },
    } as Awaited<ReturnType<typeof getCurrentTarget>>);
    render(<SettingsScreen />);
    fireEvent.press(await screen.findByText("Try again"));
    expect(await screen.findByText("2,200")).toBeTruthy();
  });

  it("reads the current singleton again when Settings regains focus", async () => {
    mockCurrent
      .mockResolvedValueOnce({
        status: 200,
        data: { id: 1, calories: 2150, protein_g: 180, fiber_g: 33 },
      } as Awaited<ReturnType<typeof getCurrentTarget>>)
      .mockResolvedValueOnce({
        status: 200,
        data: { id: 2, calories: 2200, protein_g: 175, fiber_g: 30 },
      } as Awaited<ReturnType<typeof getCurrentTarget>>);
    render(<SettingsScreen />);
    expect(await screen.findByText("2,150")).toBeTruthy();

    act(() => {
      mockFocusCallback?.();
    });

    expect(await screen.findByText("2,200")).toBeTruthy();
    expect(mockCurrent).toHaveBeenCalledTimes(2);
  });
});

describe("identity", () => {
  it("shows who is signed in", () => {
    render(<SettingsScreen />);

    expect(screen.getByText("Alex")).toBeTruthy();
    expect(screen.getByText("alex@example.com")).toBeTruthy();
  });

  it("says so plainly when Apple withheld the email", () => {
    // A private relay address or no address at all is normal here, not an
    // error, so the screen should not render an empty row.
    mockUseSession.mockReturnValue({
      status: "signedIn",
      user: { ...user, email: null },
      signIn: jest.fn(),
      signOut,
      deleteAccount,
    } as unknown as Session);

    render(<SettingsScreen />);

    expect(screen.getByText(/hiding your email/i)).toBeTruthy();
  });
});

describe("signing out", () => {
  it("calls sign-out on tap", async () => {
    render(<SettingsScreen />);

    fireEvent.press(screen.getByText("Sign out"));

    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
  });
});

describe("deleting the account", () => {
  it("asks first, and does not delete on the first tap", () => {
    render(<SettingsScreen />);

    fireEvent.press(screen.getByText("Delete my account"));

    expect(deleteAccount).not.toHaveBeenCalled();
    expect(screen.getByText("Delete your account?")).toBeTruthy();
  });

  it("names the timeline rather than asking are you sure", () => {
    // The grace period answers what deletion does before the destructive tap.
    render(<SettingsScreen />);

    fireEvent.press(screen.getByText("Delete my account"));

    expect(screen.getByText(/for 30 days/i)).toBeTruthy();
    expect(screen.getByText(/purged for good/i)).toBeTruthy();
  });

  it("backs out cleanly", () => {
    render(<SettingsScreen />);

    fireEvent.press(screen.getByText("Delete my account"));
    fireEvent.press(screen.getByText("Keep my account"));

    expect(deleteAccount).not.toHaveBeenCalled();
    expect(screen.queryByText("Delete your account?")).toBeNull();
  });

  it("deletes on the confirming tap", async () => {
    render(<SettingsScreen />);

    fireEvent.press(screen.getByText("Delete my account"));
    // The trigger is replaced by the panel, so the same label now belongs to
    // the button that actually deletes.
    fireEvent.press(screen.getByText("Delete my account"));

    await waitFor(() => expect(deleteAccount).toHaveBeenCalledTimes(1));
  });

  it("says nothing changed when the delete fails", async () => {
    deleteAccount.mockRejectedValue(new Error("boom"));

    render(<SettingsScreen />);

    fireEvent.press(screen.getByText("Delete my account"));
    fireEvent.press(screen.getByText("Delete my account"));

    await waitFor(() => expect(screen.getByText(/wasn't deleted/i)).toBeTruthy());
    // The session is untouched, because the account still exists.
    expect(screen.getByText("Alex")).toBeTruthy();
  });
});
