/**
 * The client half of Sign in with Apple.
 *
 * Kept out of the screen so the nonce rules below live in one place and can be
 * tested without rendering anything. The screen owns presentation; this owns
 * the credential.
 */

import * as AppleAuthentication from "expo-apple-authentication";
import * as Crypto from "expo-crypto";

/** Raised when the user dismisses Apple's sheet. Not an error to report. */
export class AppleSignInCancelled extends Error {
  constructor() {
    super("The user cancelled the Apple sign-in sheet.");
    this.name = "AppleSignInCancelled";
  }
}

/** Raised when Apple authorizes but hands back no identity token. */
export class AppleSignInMissingToken extends Error {
  constructor() {
    super("Apple returned a credential with no identityToken.");
    this.name = "AppleSignInMissingToken";
  }
}

/**
 * What the screen forwards to `POST /api/auth/sessions/`.
 *
 * `nonce` is the **raw** value, never the digest — see below.
 */
export type AppleCredential = {
  identityToken: string;
  nonce: string;
  name?: string;
};

/**
 * Apple's cancellation is a plain Error carrying a code, not a typed class, so
 * the code is the only thing to match on.
 */
const APPLE_CANCELLED_CODE = "ERR_REQUEST_CANCELED";

const isCancellation = (error: unknown): boolean =>
  typeof error === "object" &&
  error !== null &&
  "code" in error &&
  (error as { code?: unknown }).code === APPLE_CANCELLED_CODE;

/**
 * 32 random bytes as lowercase hex.
 *
 * Hex rather than base64url because the digest below is hex too (expo-crypto's
 * default), and one encoding for both ends of the round trip is one fewer thing
 * to get wrong. 32 bytes is well past what a replay guard needs; the nonce is
 * single-use and lives for the length of one sign-in.
 */
const generateRawNonce = (): string =>
  Array.from(Crypto.getRandomBytes(32))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");

/**
 * Joins the name parts Apple gives us, dropping the nulls.
 *
 * Returns undefined rather than an empty string when nothing is present: the
 * API treats an omitted `name` as "no news" and an empty one as a value, and
 * sending "" would overwrite a stored name with nothing.
 */
const formatName = (
  fullName: AppleAuthentication.AppleAuthenticationFullName | null,
): string | undefined => {
  const joined = [fullName?.givenName, fullName?.familyName].filter(Boolean).join(" ").trim();

  return joined.length > 0 ? joined : undefined;
};

/**
 * Presents Apple's sheet and returns what the API needs.
 *
 * **The nonce goes in hashed and comes back out raw.** The client computes
 * SHA256 of a random value and puts *that digest* on the Apple request; Apple
 * copies the string into the `nonce` claim verbatim, hashing nothing. The API
 * then hashes the raw value we send it and compares. So the digest goes to
 * Apple and the raw value goes to our server, and swapping them fails
 * verification with a 401 that looks exactly like a server bug. Doc 04 and
 * MAC-26 both spell this out because Apple's *web* flow echoes a raw nonce,
 * which is where everyone (Supabase and better-auth included) gets it wrong.
 *
 * **Name and email arrive on the first authorization only.** Every later
 * sign-in returns nulls for both. Whatever this call receives has to be
 * forwarded there and then or it is gone for that user permanently. Email is
 * not forwarded because it does not need to be: it is a signed claim inside the
 * identity token, so the server reads it from a source the client cannot forge.
 * The name is not in the token, which is why it is a request field.
 */
export const signInWithApple = async (): Promise<AppleCredential> => {
  const rawNonce = generateRawNonce();
  const hashedNonce = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, rawNonce);

  let credential: AppleAuthentication.AppleAuthenticationCredential;
  try {
    credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
      nonce: hashedNonce,
    });
  } catch (error) {
    if (isCancellation(error)) {
      throw new AppleSignInCancelled();
    }
    throw error;
  }

  if (!credential.identityToken) {
    throw new AppleSignInMissingToken();
  }

  const name = formatName(credential.fullName);

  return {
    identityToken: credential.identityToken,
    nonce: rawNonce,
    ...(name ? { name } : {}),
  };
};
