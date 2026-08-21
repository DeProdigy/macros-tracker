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
  ApiError,
  configureSession,
  getCreateSessionUrl,
  getRefreshSessionUrl,
  refreshSession,
  type RefreshOutcome,
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
 * Runs one refresh, stores the rotated pair, and reports which of the three
 * outcomes happened.
 *
 * Never throws, which is what `SessionBridge` promises the queue upstream. A
 * rejection here would be handed to every caller waiting on the shared promise
 * as a refresh failure rather than as their own original 401.
 *
 * The expired/unavailable split is the whole reason the outcome is a tagged
 * object rather than a nullable string. Upstream ends the session on `expired`,
 * so a 502 reported as one is a wrongful logout.
 *
 * Note what is stored: the response carries a **different** refresh token,
 * because MAC-25 rotates on every use and blacklists the old one. Storing only
 * the access token would leave a dead refresh token in the Keychain and log the
 * user out at the next expiry.
 */
const refresh = async (): Promise<RefreshOutcome> => {
  let refreshToken: string | null;

  try {
    refreshToken = await getRefreshToken();
  } catch {
    // SecureStore can fail on its own terms: a locked Keychain, a device the
    // user has not unlocked since boot. Read inside the guard, because a throw
    // out of here used to reach the bridge's catch and end the session over a
    // storage hiccup.
    return { status: "unavailable" };
  }

  if (!refreshToken) {
    // Nothing to present. There is no recovering this one.
    return { status: "expired" };
  }

  try {
    const response = await refreshSession({ refresh: refreshToken });

    // Unreachable at runtime: customFetch throws ApiError on any non-2xx, so
    // only 200 arrives here. It stays as a type guard — the generated response
    // is a union, and its 400/401/429 members type `data` as void, so TypeScript
    // needs the status narrowed before it will read `.access`.
    if (response.status !== 200) {
      return { status: "unavailable" };
    }

    await saveTokens({ access: response.data.access, refresh: response.data.refresh });
    return { status: "refreshed", accessToken: response.data.access };
  } catch (error) {
    // Two different failures wear the same shape here, and treating them alike
    // is how an app logs a user out on a bad train connection.
    //
    // A 400 or 401 is the server's verdict on the token itself: expired,
    // blacklisted, or attached to a deleted account. Retrying changes nothing,
    // so drop it and let the relaunch start clean.
    if (error instanceof ApiError && (error.status === 400 || error.status === 401)) {
      await clearTokens();
      return { status: "expired" };
    }

    // A timeout, a 502, a dead connection. None of them is a statement about
    // the refresh token, so it stays in the Keychain and the session stays up.
    // The caller sees its own 401 and can try again.
    return { status: "unavailable" };
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
