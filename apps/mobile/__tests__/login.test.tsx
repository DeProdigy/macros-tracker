import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { ApiError, useCreateSession } from "@macros/api-client";
import { act, fireEvent, waitFor } from "@testing-library/react-native";
import * as AppleAuthentication from "expo-apple-authentication";
import { Text } from "react-native";

import LoginScreen from "../app/(auth)/login";
import { AppleSignInCancelled, signInWithApple } from "../lib/apple-sign-in";
import { saveTokens } from "../lib/auth-storage";
import { renderWithProviders } from "../test-utils/render";

// Same seam as index.test.tsx: the generated hook. Mocking it drives every
// branch of the screen with no network.
jest.mock("@macros/api-client", () => {
  // A stand-in for the real ApiError, which the screen narrows on with
  // `instanceof` to tell a 5xx from everything else. Plain class fields rather
  // than TypeScript parameter properties: babel rewrites those into assignments
  // that jest's out-of-scope guard reads as an external reference, and the
  // suite then fails to compile.
  class ApiError extends Error {
    status: number;
    body: unknown;

    constructor(status: number, body: unknown) {
      super(`API request failed with status ${status}`);
      this.status = status;
      this.body = body;
    }
  }

  return { useCreateSession: jest.fn(), ApiError };
});

// The two helpers are unit-tested on their own (apple-sign-in.test.ts). Here
// they are stubbed so the screen's state machine is what is under test, not
// the nonce arithmetic a second time.
jest.mock("../lib/apple-sign-in", () => {
  class AppleSignInCancelled extends Error {}

  return {
    signInWithApple: jest.fn(),
    AppleSignInCancelled,
  };
});

jest.mock("../lib/auth-storage", () => ({
  saveTokens: jest.fn(),
}));

// AppleAuthenticationButton is a native view, so it is replaced with a pressable
// Text. The factory only declares the mock: jest hoists it above the imports, so
// it cannot close over `Text`. The implementation is supplied in beforeEach.
jest.mock("expo-apple-authentication", () => ({
  isAvailableAsync: jest.fn(),
  AppleAuthenticationButton: jest.fn(),
  AppleAuthenticationButtonStyle: { BLACK: 0, WHITE: 2 },
  AppleAuthenticationButtonType: { CONTINUE: 1 },
}));

const mockUseCreateSession = useCreateSession as jest.MockedFunction<typeof useCreateSession>;
const mockSignInWithApple = signInWithApple as jest.MockedFunction<typeof signInWithApple>;
const mockSaveTokens = saveTokens as jest.MockedFunction<typeof saveTokens>;
const mockIsAvailableAsync = AppleAuthentication.isAvailableAsync as jest.MockedFunction<
  typeof AppleAuthentication.isAvailableAsync
>;
const mockAppleButton =
  AppleAuthentication.AppleAuthenticationButton as unknown as jest.MockedFunction<
    (props: { onPress: () => void }) => React.ReactElement
  >;

type CreateSessionResult = ReturnType<typeof useCreateSession>;

/**
 * The screen reads exactly one field off the mutation result. Building a full
 * `UseMutationResult` would be ~20 fields of noise per test, so supply the one
 * and cast — still checked against the real type, so a rename fails here too.
 */
const sessionMutation = (mutateAsync: CreateSessionResult["mutateAsync"]): CreateSessionResult =>
  ({ mutateAsync }) as CreateSessionResult;

const successResponse = {
  status: 201,
  data: { access: "access-token", refresh: "refresh-token", created: true, user: {} },
} as Awaited<ReturnType<CreateSessionResult["mutateAsync"]>>;

const credential = {
  identityToken: "an.identity.token",
  nonce: "the-raw-nonce",
  name: "Ada Lovelace",
};

describe("LoginScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAppleButton.mockImplementation(({ onPress }) => (
      <Text onPress={onPress}>Continue with Apple</Text>
    ));
    mockIsAvailableAsync.mockResolvedValue(true);
    mockSaveTokens.mockResolvedValue(undefined);
  });

  it("renders the welcome copy, the one button and the AI disclosure", async () => {
    mockUseCreateSession.mockReturnValue(sessionMutation(jest.fn() as never));

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    expect(screen.getByText("Macros")).toBeTruthy();
    expect(screen.getByText(/photograph a meal/i)).toBeTruthy();
    expect(screen.getByText("Continue with Apple")).toBeTruthy();
    // Doc 26: the line that replaced the Register / Log in toggle.
    expect(screen.getByText(/same button/i)).toBeTruthy();
    // Doc 26: the disclosure belongs before the tap, not in Settings.
    expect(screen.getByText(/sent to an ai provider/i)).toBeTruthy();
  });

  it("posts the raw nonce, the token and the name, then stores both tokens", async () => {
    const mutateAsync = jest.fn(async () => successResponse);
    mockUseCreateSession.mockReturnValue(sessionMutation(mutateAsync as never));
    mockSignInWithApple.mockResolvedValue(credential);

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        data: {
          identity_token: "an.identity.token",
          nonce: "the-raw-nonce",
          name: "Ada Lovelace",
        },
      }),
    );

    await waitFor(() =>
      expect(mockSaveTokens).toHaveBeenCalledWith({
        access: "access-token",
        refresh: "refresh-token",
      }),
    );
  });

  it("omits name from the request when Apple sent none", async () => {
    // An explicit `name: undefined` would serialize the key out of the JSON
    // anyway, but asserting the key is absent is what stops a later refactor
    // from sending an empty string and wiping a stored name.
    const mutateAsync = jest.fn(async () => successResponse);
    mockUseCreateSession.mockReturnValue(sessionMutation(mutateAsync as never));
    mockSignInWithApple.mockResolvedValue({
      identityToken: "an.identity.token",
      nonce: "the-raw-nonce",
    });

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    // toHaveBeenCalledWith is an exact match on the argument, so an extra
    // `name` key of any value fails this.
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        data: { identity_token: "an.identity.token", nonce: "the-raw-nonce" },
      }),
    );
  });

  it("shows the three named verifying lines while the call is in flight", async () => {
    // Doc 26 is explicit that 9c is three named lines rather than a spinner, so
    // the assertion is on the names, not on the presence of an indicator.
    let resolveMutation: (value: typeof successResponse) => void = () => {};
    const mutateAsync = jest.fn(
      () =>
        new Promise<typeof successResponse>((resolve) => {
          resolveMutation = resolve;
        }),
    );
    mockUseCreateSession.mockReturnValue(sessionMutation(mutateAsync as never));
    mockSignInWithApple.mockResolvedValue(credential);

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    await waitFor(() => expect(screen.getByText("Verifying")).toBeTruthy());
    expect(screen.getByText(/confirming it's you with apple/i)).toBeTruthy();
    expect(screen.getByText(/checking your apple token/i)).toBeTruthy();
    expect(screen.getByText(/saving your session/i)).toBeTruthy();
    // The welcome screen is gone while this runs, not layered under a spinner.
    expect(screen.queryByText("Continue with Apple")).toBeNull();

    await act(async () => {
      resolveMutation(successResponse);
    });
  });

  it("returns to the welcome screen with no error when the sheet is cancelled", async () => {
    // Dismissing Apple's sheet is a choice. Showing an error for it blames the
    // user for the thing they just decided to do.
    mockUseCreateSession.mockReturnValue(sessionMutation(jest.fn() as never));
    mockSignInWithApple.mockRejectedValue(new AppleSignInCancelled());

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    await waitFor(() => expect(screen.getByText("Continue with Apple")).toBeTruthy());
    expect(screen.queryByText(/didn't go through/i)).toBeNull();
    expect(mockSaveTokens).not.toHaveBeenCalled();
  });

  it("blames the credential when the API answers 401", async () => {
    const mutateAsync = jest.fn(async () => {
      throw new ApiError(401, { detail: "Could not verify the Apple credential." });
    });
    mockUseCreateSession.mockReturnValue(sessionMutation(mutateAsync as never));
    mockSignInWithApple.mockResolvedValue(credential);

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    await waitFor(() => expect(screen.getByText(/didn't go through/i)).toBeTruthy());
    expect(screen.queryByText(/on our end/i)).toBeNull();
    // Recoverable means the button is still there, not that a message replaced it.
    expect(screen.getByText("Continue with Apple")).toBeTruthy();
    expect(mockSaveTokens).not.toHaveBeenCalled();
  });

  it("blames the server, not the user, when the API answers 500", async () => {
    // Found on a real device: APPLE_CLIENT_ID was unset in Railway, so the
    // verifier raised ImproperlyConfigured and every attempt was a 500. The
    // screen said "try again" twice, and retrying could not have worked. A 5xx
    // has to read as somebody else's problem or the advice is a lie.
    const mutateAsync = jest.fn(async () => {
      throw new ApiError(500, "<html>Server Error</html>");
    });
    mockUseCreateSession.mockReturnValue(sessionMutation(mutateAsync as never));
    mockSignInWithApple.mockResolvedValue(credential);

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    await waitFor(() => expect(screen.getByText(/on our end/i)).toBeTruthy());
    expect(screen.queryByText(/didn't go through/i)).toBeNull();
    expect(screen.getByText("Continue with Apple")).toBeTruthy();
    expect(mockSaveTokens).not.toHaveBeenCalled();
  });

  it("does not store tokens when Apple's sign-in itself fails", async () => {
    mockUseCreateSession.mockReturnValue(sessionMutation(jest.fn() as never));
    mockSignInWithApple.mockRejectedValue(new Error("ERR_INVALID_RESPONSE"));

    const screen = renderWithProviders(<LoginScreen />);
    await waitFor(() => expect(mockIsAvailableAsync).toHaveBeenCalled());

    fireEvent.press(screen.getByText("Continue with Apple"));

    await waitFor(() => expect(screen.getByText(/didn't go through/i)).toBeTruthy());
    expect(mockSaveTokens).not.toHaveBeenCalled();
  });

  it("explains itself instead of offering a dead button when Apple auth is unavailable", async () => {
    mockUseCreateSession.mockReturnValue(sessionMutation(jest.fn() as never));
    mockIsAvailableAsync.mockResolvedValue(false);

    const screen = renderWithProviders(<LoginScreen />);

    await waitFor(() => expect(screen.getByText(/isn't available on this device/i)).toBeTruthy());
    expect(screen.queryByText("Continue with Apple")).toBeNull();
  });
});
