import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import * as AppleAuthentication from "expo-apple-authentication";
import * as Crypto from "expo-crypto";

import {
  AppleSignInCancelled,
  AppleSignInMissingToken,
  signInWithApple,
} from "../lib/apple-sign-in";

// Both are native modules with no JS implementation off-device, so they are the
// seam. What is under test is the shape of the call we make to Apple and the
// shape of what we hand back — the two places the nonce can be sent the wrong
// way round.
jest.mock("expo-apple-authentication", () => ({
  signInAsync: jest.fn(),
  AppleAuthenticationScope: { FULL_NAME: 0, EMAIL: 1 },
}));

jest.mock("expo-crypto", () => ({
  getRandomBytes: jest.fn(),
  digestStringAsync: jest.fn(),
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
}));

const mockSignInAsync = AppleAuthentication.signInAsync as jest.MockedFunction<
  typeof AppleAuthentication.signInAsync
>;
const mockGetRandomBytes = Crypto.getRandomBytes as jest.MockedFunction<
  typeof Crypto.getRandomBytes
>;
const mockDigestStringAsync = Crypto.digestStringAsync as jest.MockedFunction<
  typeof Crypto.digestStringAsync
>;

/** 32 bytes of 0xab, so the hex nonce is a known, checkable string. */
const FIXED_BYTES = new Uint8Array(32).fill(0xab);
const EXPECTED_RAW_NONCE = "ab".repeat(32);
const FAKE_DIGEST = "sha256-of-the-raw-nonce";

const credential = (
  partial: Partial<AppleAuthentication.AppleAuthenticationCredential>,
): AppleAuthentication.AppleAuthenticationCredential =>
  ({
    user: "apple-sub-123",
    state: null,
    fullName: null,
    email: null,
    identityToken: "an.identity.token",
    authorizationCode: "code",
    ...partial,
  }) as AppleAuthentication.AppleAuthenticationCredential;

describe("signInWithApple", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetRandomBytes.mockReturnValue(FIXED_BYTES);
    mockDigestStringAsync.mockResolvedValue(FAKE_DIGEST);
  });

  it("sends the digest to Apple and returns the raw nonce for the API", async () => {
    // The single most breakable rule in this flow. Apple hashes nothing in the
    // native flow, so the digest has to go out and the raw value has to come
    // back. Swapping them fails server-side verification with a 401 that reads
    // like a server bug, which is why it gets its own assertion on both halves.
    mockSignInAsync.mockResolvedValue(credential({}));

    const result = await signInWithApple();

    expect(mockDigestStringAsync).toHaveBeenCalledWith(
      Crypto.CryptoDigestAlgorithm.SHA256,
      EXPECTED_RAW_NONCE,
    );
    expect(mockSignInAsync).toHaveBeenCalledWith(expect.objectContaining({ nonce: FAKE_DIGEST }));
    expect(result.nonce).toBe(EXPECTED_RAW_NONCE);
    expect(result.identityToken).toBe("an.identity.token");
  });

  it("requests the name and email scopes", async () => {
    // Requested on every sign-in even though Apple answers only on the first:
    // there is no way to know from the client which authorization is the first.
    mockSignInAsync.mockResolvedValue(credential({}));

    await signInWithApple();

    expect(mockSignInAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      }),
    );
  });

  it("forwards the name when Apple supplies one", async () => {
    mockSignInAsync.mockResolvedValue(
      credential({
        fullName: {
          namePrefix: null,
          givenName: "Ada",
          middleName: null,
          familyName: "Lovelace",
          nameSuffix: null,
          nickname: null,
        },
      }),
    );

    const result = await signInWithApple();

    expect(result.name).toBe("Ada Lovelace");
  });

  it("omits the name entirely when Apple supplies nothing", async () => {
    // Every sign-in after the first. An empty string here would overwrite the
    // name the server stored on the first authorization, and Apple will never
    // send it again — the one unfixable bug on this path.
    mockSignInAsync.mockResolvedValue(credential({ fullName: null }));

    const result = await signInWithApple();

    expect(result.name).toBeUndefined();
    expect(Object.keys(result)).not.toContain("name");
  });

  it("uses whichever name part is present", async () => {
    mockSignInAsync.mockResolvedValue(
      credential({
        fullName: {
          namePrefix: null,
          givenName: "Ada",
          middleName: null,
          familyName: null,
          nameSuffix: null,
          nickname: null,
        },
      }),
    );

    const result = await signInWithApple();

    expect(result.name).toBe("Ada");
  });

  it("maps Apple's cancellation code to AppleSignInCancelled", async () => {
    mockSignInAsync.mockRejectedValue(
      Object.assign(new Error("canceled"), {
        code: "ERR_REQUEST_CANCELED",
      }),
    );

    await expect(signInWithApple()).rejects.toBeInstanceOf(AppleSignInCancelled);
  });

  it("rethrows any other Apple error unchanged", async () => {
    const failure = Object.assign(new Error("boom"), { code: "ERR_INVALID_RESPONSE" });
    mockSignInAsync.mockRejectedValue(failure);

    await expect(signInWithApple()).rejects.toBe(failure);
  });

  it("rejects a credential with no identity token", async () => {
    // Apple can authorize and still return a null token. Posting null to the
    // API would be a 400 from a state the user believes succeeded.
    mockSignInAsync.mockResolvedValue(credential({ identityToken: null }));

    await expect(signInWithApple()).rejects.toBeInstanceOf(AppleSignInMissingToken);
  });
});
