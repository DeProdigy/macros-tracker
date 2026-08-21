/**
 * Token storage, Keychain-backed.
 *
 * `expo-secure-store` writes to the iOS Keychain (and the Android Keystore),
 * so the values are encrypted at rest and survive an app restart without ever
 * sitting on disk in plaintext. AsyncStorage is the wrong tool here and doc 04
 * says so explicitly: it is a plaintext file, readable from a backup or a
 * jailbroken device, and a refresh token is a long-lived credential.
 *
 * Values are namespaced with a `macros.` prefix because SecureStore keys share
 * one flat keychain service per app.
 */

import * as SecureStore from "expo-secure-store";

const ACCESS_TOKEN_KEY = "macros.auth.access";
const REFRESH_TOKEN_KEY = "macros.auth.refresh";

export type AuthTokens = {
  access: string;
  refresh: string;
};

/**
 * Writes both tokens.
 *
 * Sequential rather than `Promise.all` on purpose: the two writes are not
 * atomic either way, but ordering them means a failure leaves at most the
 * access token stored, never a refresh token with no access token beside it.
 * MAC-31 reads the pair, and a half-written pair is the state it cannot
 * interpret.
 */
export const saveTokens = async ({ access, refresh }: AuthTokens): Promise<void> => {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, access);
  await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refresh);
};

/**
 * Reads the access token on its own.
 *
 * Separate from `getTokens` because `customFetch` needs only this half on every
 * request, and reading the refresh token it will not use means one more
 * Keychain hit per call.
 */
export const getAccessToken = (): Promise<string | null> =>
  SecureStore.getItemAsync(ACCESS_TOKEN_KEY);

/** Reads the refresh token on its own. Used by the refresh and sign-out calls. */
export const getRefreshToken = (): Promise<string | null> =>
  SecureStore.getItemAsync(REFRESH_TOKEN_KEY);

/** Reads the stored pair, or null when either half is missing. */
export const getTokens = async (): Promise<AuthTokens | null> => {
  const [access, refresh] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  ]);

  if (!access || !refresh) {
    return null;
  }

  return { access, refresh };
};

/** Removes both tokens. Used by sign-out and by the 401 handler in MAC-31. */
export const clearTokens = async (): Promise<void> => {
  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
};
