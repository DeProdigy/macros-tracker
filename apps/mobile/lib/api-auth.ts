/**
 * Wires the generated client's auth policy to this app's Keychain.
 *
 * `packages/api-client` owns *what* happens on a 401 — one refresh, shared by
 * every waiting caller, then one retry. This file owns *how*: which store the
 * tokens come out of, which endpoint mints new ones, and what "give up" means.
 *
 * The dependency points this way on purpose. The package cannot import
 * `expo-secure-store` without becoming Expo-only, and it cannot import the
 * generated `refreshSession` at all, because every generated operation imports
 * `customFetch` from the package's own http-client. That is a cycle.
 */

import {
  configureSession,
  getCreateSessionUrl,
  getRefreshSessionUrl,
  refreshSession,
} from "@macros/api-client";

import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from "./auth-storage";

let sessionExpiredListener: (() => void) | null = null;

/**
 * Registers the one callback that runs when a session cannot be recovered.
 *
 * A module-level slot rather than a subscriber list: there is exactly one
 * session in the app, so a second listener would mean two things believe they
 * own routing to Welcome. `SessionProvider` claims it on mount and releases it
 * on unmount.
 */
export const setSessionExpiredListener = (listener: (() => void) | null): void => {
  sessionExpiredListener = listener;
};

/**
 * Runs one refresh, stores the rotated pair, and answers with the new access
 * token — or null when the session is gone for good.
 *
 * Never throws, which is what `SessionBridge` promises the queue upstream. A
 * rejection here would be handed to every caller waiting on the shared promise
 * as a refresh failure rather than as their own original 401.
 *
 * Note what is stored: the response carries a **different** refresh token,
 * because MAC-25 rotates on every use and blacklists the old one. Storing only
 * the access token would leave a dead refresh token in the Keychain and log the
 * user out at the next expiry.
 */
const refresh = async (): Promise<string | null> => {
  const refreshToken = await getRefreshToken();

  if (!refreshToken) {
    return null;
  }

  try {
    const response = await refreshSession({ refresh: refreshToken });

    if (response.status !== 200) {
      await clearTokens();
      return null;
    }

    await saveTokens({ access: response.data.access, refresh: response.data.refresh });
    return response.data.access;
  } catch {
    // Every failure is the same failure from here: the refresh token is
    // expired, blacklisted, or belongs to a deleted account, and no amount of
    // retrying changes that. Clear it so a relaunch does not try again.
    await clearTokens();
    return null;
  }
};

/**
 * Installs the bridge. Called once, at module load, before anything renders.
 *
 * Not in an effect: a request fired during the first render would otherwise go
 * out with no Authorization header and no retry policy behind it.
 */
export const installApiAuth = (): void => {
  configureSession({
    getAccessToken,
    refresh,
    onSessionExpired: () => sessionExpiredListener?.(),

    // Sign-in and refresh both carry their own credential in the body, so a 401
    // from either is a verdict on that credential, not on an expired access
    // token. Refreshing in response would loop against an endpoint that was
    // never going to succeed. Taken from the generated URL helpers rather than
    // written out, so a route rename cannot leave this list quietly stale.
    publicPaths: [getCreateSessionUrl(), getRefreshSessionUrl()],

    // The refresh call opts out of the client-side deadline, and this is the
    // one genuinely uncomfortable trade in MAC-31.
    //
    // Aborting a refresh does not cancel it. The server may already have
    // rotated the token and blacklisted the one still sitting in our Keychain,
    // and we would be throwing away the only copy of its replacement. That is
    // the self-inflicted logout this whole ticket exists to prevent, so a
    // 15-second timer is the wrong tool. iOS's own request timeout, around 60
    // seconds, remains the backstop.
    untimedPaths: [getRefreshSessionUrl()],
  });
};
