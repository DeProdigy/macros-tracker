# MAC-71: Fix photo upload to R2 failing on iOS

Linear:
[MAC-71](https://linear.app/hintology/issue/MAC-71/fix-photo-upload-to-r2-failing-on-ios).

## Problem

On a physical iPhone, photo analysis fails. The photo screen shows "Could not analyze this photo.
Retry or use Manual."

MAC-70 (#54) made the app launch again. This bug was hidden until then, because every iOS build
since MAC-54 closed at launch.

## Evidence

Railway logs show `POST /api/uploads/` with 200 from the iPhone. No `POST /api/analyses/` follows.
So the failure is the direct `PUT` to R2 in `apps/mobile/lib/photo-analysis.ts`.

A temporary `[DEBUG-r2put]` log on the device, 15 Sep 2026 20:57 UTC:

```
blobSize: 359022, blobType: "", status: 403
<Error><Code>SignatureDoesNotMatch</Code>...
```

## Root cause

- `presign_upload` in `apps/api/uploads/services.py` signs `ContentType: image/jpeg` and
  `ContentLength` into the URL. R2 rejects a `PUT` whose headers differ from the signed values.
- The app reads the compressed photo with `fetch(file://...).blob()`. The file response has no
  `content-type`, so `blob.type` is `""`.
- Expo replaces the global `fetch`. For a `Blob` body, `normalizeBodyInitAsync` in
  `expo/src/winter/fetch/RequestUtils.ts` overwrites `Content-Type` with `blob.type`. It does this
  even when the caller already set the header.
- The app sets `Content-Type: image/jpeg`, and Expo sends `""`. The signature does not match, and
  R2 answers 403.
- The size matches the signed value, so `Content-Length` is not the cause.
- The Expo code is the same in 57.0.8 and 57.0.23. MAC-70 did not cause this.

## Files touched

- `apps/mobile/lib/photo-analysis.ts`
- `apps/mobile/__tests__/photo-analysis.test.ts`
- `plans/tickets/MAC-71.md`

## Approach

Send the photo as bytes, not as a `Blob`.

```ts
const bytes = new Uint8Array(await imageResponse.arrayBuffer());
const upload = await presignUpload({
  content_type: "image/jpeg",
  content_length: bytes.byteLength,
});
await fetch(uploadData.url, {
  method: "PUT",
  headers: { "Content-Type": "image/jpeg", "Content-Length": String(bytes.byteLength) },
  body: bytes,
});
```

Expo passes a typed array through without changing headers. That is the `ArrayBuffer.isView` branch
in `RequestUtils.ts`. A code comment explains why the body must not be a `Blob`. The change also
removes the React Native Blob base64 copy that the dev warning reports.

## Regression test

`__tests__/photo-analysis.test.ts` gains one test. It asserts that the `PUT` body is a `Uint8Array`,
`Content-Type` is `image/jpeg`, and `Content-Length` equals the presigned length. The test failed on
the old code first, with `TypeError: imageResponse.blob is not a function`.

This test is shallow. Jest mocks `fetch`, so the test cannot run Expo's native header logic. It
stops a return to a `Blob` body. It cannot detect a future Expo change to typed-array bodies. The
device run is the real proof.

## Verification

1. The new test fails, then passes after the change. Done.
2. `pnpm pre-pr` passes.
3. On the iPhone development build: the upload returns 200, analysis items appear, and Railway logs
   show `POST /api/analyses/` with 201. Alex runs this step.
4. Remove the `[DEBUG-r2put]` logs. `git diff` shows only the planned files.

## Alternatives rejected

- **Wrap the blob:** `new Blob([blob], { type: "image/jpeg" })`. React Native's `Blob` constructor
  has limited part support. It also keeps the base64 copy.
- **Stop signing `ContentType` on the server.** The signed type is a security control. It stops a
  URL holder from uploading other content types.
- **Upload with `expo-file-system`.** It works, but it adds a native module. That means a new EAS
  build for a JS-only bug.
- **Add `expo-blob`.** Also native, and it does not change the header override.

## Concepts in play

- **SigV4 presigned URLs.** The signature covers the method, path, query, and each signed header.
  Change one signed header value, and the signature fails. R2 cannot tell you which header was
  wrong. It returns only the hash of what it expected.
- **Fetch spec versus Expo.** The Fetch spec sets `Content-Type` from a body only when the caller
  did not set one. Expo sets it always for `Blob` and `FormData`. A deviation like this causes bugs
  that a test with a mocked `fetch` cannot catch.
- **Why the error looked generic.** `photo.tsx` maps every non-429 failure to one message. That is
  right for users, and it hid the 403 from us.

## Horizontal ticket

This is a bug fix, not a slice. A user can now photograph food and get an estimate.

## Blast radius

One function, and only the photo flow. No API change. No native change, so the existing development
build gets the fix from Metro. A preview build must be rebuilt, because it contains its own JS
bundle.

## Deliberately unhandled

- **Report the Expo header override upstream.** It is an outward-facing action. Alex decides.
- **A clearer message for upload failures.** The current copy is fine for users.
- **A device-level upload test in CI.** Same missing seam as MAC-70.

## Open questions

1. **Stack on MAC-70.** Resolved. #54 merged to `main`, so this branch starts from `main`.
