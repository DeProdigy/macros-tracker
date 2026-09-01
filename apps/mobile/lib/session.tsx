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
  updateCurrentUser,
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
import { AppState } from "react-native";

import { installApiAuth, setSessionExpiredListener } from "./api-auth";
import { clearTokens, getRefreshToken, getTokens } from "./auth-storage";
import { deviceTimezone, type TimezoneSyncStatus } from "./local-day";

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
  /** Whether day-based requests can safely use the cached user timezone. */
  timezoneStatus: TimezoneSyncStatus;
  /** Adopts the user the sign-in call returned. Tokens are already in the Keychain by then. */
  signIn: (user: User) => void;
  /**
   * Replace the cached user after a write that changed it.
   *
   * Separate from `signIn`, which takes the same argument and does nearly the
   * same thing. Calling `signIn` from a target screen would read as signing
   * someone in, and a name that lies costs more than the five lines it saves.
   *
   * MAC-47 added this, then removed it when the sequencing reversal deleted its
   * only caller. MAC-50 brings it back with the caller that needs it: saving a
   * first target flips `onboarding_completed` on the server, and the route
   * guard reads the session rather than the network.
   */
  updateUser: (user: User) => void;
  /** Blacklists the refresh token, clears the Keychain, empties the cache. */
  signOut: () => Promise<void>;
  /** Soft-deletes the account, then does everything sign-out does. */
  deleteAccount: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

/**
 * Best-effort blacklist of a refresh token, twice if the 401 handler moved it.
 *
 * The second attempt exists because sign-out is the one call whose *body* is a
 * credential. With an expired access token the DELETE 401s, `customFetch`
 * refreshes — which rotates the refresh token and blacklists the copy already
 * captured in this request's body — and then retries with that same dead copy.
 * The server answers 400, and the token it just minted would live out its full
 * 30 days on the server while this device throws away its only copy. That is
 * the opposite of what sign-out promises.
 *
 * Re-reading the Keychain is what distinguishes the two failures. A different
 * token there means a rotation happened underneath this call and the new one is
 * what needs revoking; the same token means the request failed for its own
 * reasons — no network, an already-blacklisted token — and repeating it would
 * only fail again.
 *
 * Bounded at two attempts on purpose. The retry carries the access token minted
 * moments earlier, so a third round is not a state the 401 path can reach.
 */
const revokeRefreshToken = async (token: string): Promise<void> => {
  try {
    // The refresh token in the body of a DELETE, which looks wrong and is
    // right: an access token cannot be revoked, so the refresh token is the
    // only thing there is to destroy.
    await deleteCurrentSession({ refresh: token });
    return;
  } catch {
    // Fall through to the rotation check. Every other cause is handled by
    // sending nothing further.
  }

  const rotated = await getRefreshToken();

  if (!rotated || rotated === token) {
    return;
  }

  try {
    await deleteCurrentSession({ refresh: rotated });
  } catch {
    // Already expired, already blacklisted, or the network is down. None of
    // those should keep the user signed in on this device.
  }
};

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
  const [timezoneStatus, setTimezoneStatus] = useState<TimezoneSyncStatus>("unavailable");
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
  //
  // Reuses endSession rather than clearing the cache inline: expiry can arrive
  // with storage half-emptied (a missing refresh token, a failed clear), and a
  // stale access token left in the Keychain is one customFetch attaches to the
  // next request. One teardown path means one definition of signed out.
  useEffect(() => {
    setSessionExpiredListener(() => {
      void endSession();
    });

    return () => setSessionExpiredListener(null);
  }, [endSession]);

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
      } catch (error) {
        // Which failure this was decides whether the tokens survive, and the
        // wrong answer here is unrecoverable: a cold start in airplane mode
        // would wipe the Keychain, and turning the radio back on would not
        // bring the session back.
        //
        // 401 and 403 are the server's verdict on the credential — refused, or
        // attached to an account that is gone. Nothing to keep.
        //
        // A timeout, a 5xx, a dead connection: no verdict was ever reached.
        // The user still sees Welcome, because there is no session to show
        // them yet, but the tokens stay and the next launch with signal
        // restores them. This mirrors the expired/unavailable split the
        // refresh bridge makes, and the two disagreeing is what made this a
        // bug rather than a rough edge.
        const refused = error instanceof ApiError && (error.status === 401 || error.status === 403);

        if (refused) {
          await clearTokens();
        }

        if (!cancelled) setState({ status: "signedOut" });
      }
    };

    void restore();

    return () => {
      cancelled = true;
    };
  }, []);

  // Authentication succeeds before this best-effort synchronization starts.
  // Food requests need the result, but the user can still reach the app when
  // timezone detection or the network is unavailable.
  useEffect(() => {
    if (state.status !== "signedIn") {
      setTimezoneStatus("unavailable");
      return;
    }

    let active = true;
    let syncInFlight = false;

    const syncTimezone = async () => {
      if (syncInFlight) return;
      syncInFlight = true;
      setTimezoneStatus("syncing");

      const timezone = deviceTimezone();
      if (!timezone) {
        if (active) setTimezoneStatus("unavailable");
        syncInFlight = false;
        return;
      }

      if (timezone === state.user.timezone) {
        if (active) setTimezoneStatus("ready");
        syncInFlight = false;
        return;
      }

      try {
        const response = await updateCurrentUser({ timezone });
        if (!active) return;
        if (response.status !== 200) {
          throw new Error(`Unexpected user-update status: ${response.status}`);
        }
        setState((current) =>
          current.status === "signedIn" ? { status: "signedIn", user: response.data } : current,
        );
        setTimezoneStatus("ready");
      } catch {
        if (active) setTimezoneStatus("unavailable");
      } finally {
        syncInFlight = false;
      }
    };

    void syncTimezone();
    const subscription = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active") void syncTimezone();
    });

    return () => {
      active = false;
      subscription.remove();
    };
  }, [state.status, state.status === "signedIn" ? state.user.timezone : null]);

  const signIn = useCallback((user: User) => setState({ status: "signedIn", user }), []);

  const updateUser = useCallback(
    (user: User) =>
      // Only while signed in. A response can land after the global 401 handler
      // has signed the user out, and writing state unconditionally would put
      // the app back into a session the server already rejected.
      setState((current) =>
        current.status === "signedIn" ? { status: "signedIn", user } : current,
      ),
    [],
  );

  const signOut = useCallback(async () => {
    const refreshToken = await getRefreshToken();

    if (refreshToken) {
      await revokeRefreshToken(refreshToken);
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
    () => ({ ...state, timezoneStatus, signIn, updateUser, signOut, deleteAccount }),
    [state, timezoneStatus, signIn, updateUser, signOut, deleteAccount],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
};
