/**
 * The app's one piece of auth state, and the source every route reads.
 *
 * expo-router routes from state rather than from imperative navigation: screens
 * render a `<Redirect>` based on what the session says, and moving the session
 * moves the app. The alternative — calling `router.replace` from wherever a
 * logout happens — means every future caller has to remember to do it, and the
 * global 401 handler has no component to call it from at all.
 */

import {
  ApiError,
  deleteCurrentSession,
  deleteCurrentUser,
  getCurrentUser,
  type User,
} from "@macros/api-client";
import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { installApiAuth, setSessionExpiredListener } from "./api-auth";
import { clearTokens, getRefreshToken, getTokens } from "./auth-storage";

// At module load, so the bridge is in place before the first render can fire a
// request. See installApiAuth for why this is not an effect.
installApiAuth();

/**
 * Three states, not two.
 *
 * `loading` is a real state and the splash screen is its UI. Collapsing it into
 * `signedOut` is how an app shows a returning user a flash of Welcome before
 * correcting itself, which reads as being logged out and is the specific thing
 * doc 26 puts the gate behind the splash to avoid.
 */
export type SessionState =
  { status: "loading" } | { status: "signedOut" } | { status: "signedIn"; user: User };

export type Session = SessionState & {
  /** Adopts the user the sign-in call returned. Tokens are already in the Keychain by then. */
  signIn: (user: User) => void;
  /** Blacklists the refresh token, clears the Keychain, empties the cache. */
  signOut: () => Promise<void>;
  /** Soft-deletes the account, then does everything sign-out does. */
  deleteAccount: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

/** Reads the session. Throws outside the provider rather than returning a fake signed-out. */
export const useSession = (): Session => {
  const session = useContext(SessionContext);

  if (!session) {
    throw new Error("useSession must be used inside <SessionProvider>.");
  }

  return session;
};

export const SessionProvider = ({ children }: { children: ReactNode }) => {
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const queryClient = useQueryClient();

  /**
   * Local teardown. Runs whether or not the server was reachable.
   *
   * Sign-out that depends on a successful request is sign-out that fails on a
   * train. The server call is best-effort; dropping the tokens is not.
   */
  const endSession = useCallback(async () => {
    await clearTokens();
    // Otherwise the next user to sign in on this device sees the previous
    // user's cached responses until each query refetches.
    queryClient.clear();
    setState({ status: "signedOut" });
  }, [queryClient]);

  // The global 401 handler has no component to navigate from, so it moves this
  // state instead and every guarded route follows.
  useEffect(() => {
    setSessionExpiredListener(() => {
      queryClient.clear();
      setState({ status: "signedOut" });
    });

    return () => setSessionExpiredListener(null);
  }, [queryClient]);

  // The launch gate. A token in the Keychain is not a session: it may be
  // expired, blacklisted, or attached to an account that has since been
  // deleted. Only the server knows, so ask it once, at launch.
  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      const tokens = await getTokens();

      if (!tokens) {
        if (!cancelled) setState({ status: "signedOut" });
        return;
      }

      try {
        // Goes through customFetch, so an expired access token is refreshed and
        // retried here before it ever looks like a failure.
        const response = await getCurrentUser();

        if (!cancelled) {
          setState(
            response.status === 200
              ? { status: "signedIn", user: response.data }
              : { status: "signedOut" },
          );
        }
      } catch {
        await clearTokens();
        if (!cancelled) setState({ status: "signedOut" });
      }
    };

    void restore();

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback((user: User) => setState({ status: "signedIn", user }), []);

  const signOut = useCallback(async () => {
    const refreshToken = await getRefreshToken();

    try {
      if (refreshToken) {
        // The refresh token in the body of a DELETE, which looks wrong and is
        // right: an access token cannot be revoked, so the refresh token is the
        // only thing there is to destroy.
        await deleteCurrentSession({ refresh: refreshToken });
      }
    } catch {
      // Already expired, already blacklisted, or the network is down. None of
      // those should keep the user signed in on this device.
    }

    await endSession();
  }, [endSession]);

  const deleteAccount = useCallback(async () => {
    try {
      await deleteCurrentUser();
    } catch (error) {
      // A 401 means the account is already deactivated — deleting twice is a
      // no-op the API documents. Anything else failed for real, so keep the
      // session and let Settings say so, rather than signing someone out of an
      // account that still exists.
      if (!(error instanceof ApiError) || error.status !== 401) {
        throw error;
      }
    }

    await endSession();
  }, [endSession]);

  const value = useMemo<Session>(
    () => ({ ...state, signIn, signOut, deleteAccount }),
    [state, signIn, signOut, deleteAccount],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
};
