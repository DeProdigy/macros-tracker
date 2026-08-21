# MAC-30 — Mobile: Sign in with Apple on Welcome

Approved 21 Aug 2026. Linear:
[MAC-30](https://linear.app/hintology/issue/MAC-30/mobile-sign-in-with-apple-on-welcome).

## Context

The first screen a new user sees and the only one in the auth flow that is ours.
Doc 26 cut auth from four screens to three, and one of the three is Apple's own
sheet. The screen ends with an access and refresh token in the Keychain.
Everything after that — the session gate, the global 401 handler, routing to
Today — is MAC-31.

## Shipped against a blocker, deliberately

MAC-30 is blocked by MAC-20, which needs an Apple Developer membership that
lapsed in 2019 and an EAS development build that does not exist yet
(`apps/mobile/eas.json` is absent). `expo-apple-authentication` is a native
module behind an entitlement, so Expo Go cannot run it and the simulator cannot
satisfy the ticket either.

Two acceptance criteria are therefore **not met by this PR** and stay open:

- entitlement present in the build
- verified on a physical device

Everything else is done and gated by CI. The config plugin is registered, so the
entitlement lands automatically the first time a build runs. The decision to
build the code now rather than wait was made explicitly: renewal has a 24 to 48
hour lead time, and none of the code below depends on its outcome.

## The correction to the ticket

The ticket says *"Name and email forwarded when Apple supplies them"*. There is
no email field to forward to. `SessionCreateRequest`, generated from MAC-27's
schema, carries exactly `identity_token`, `nonce` and an optional `name`.

That is correct and should not change. Email is a signed claim inside the
identity token, so the server reads it from a source the client cannot forge —
MAC-26's `verify_apple_identity_token` returns it on `AppleIdentity`. The name is
*not* in the token, which is precisely why it has to be a request field and why
it is documented as unverified and display-only. Adding an `email` field would
mean trusting the client for a value the server already has a better copy of.

So: the name is forwarded, the email is not, and the first-authorization trap is
fully handled.

## Files touched

| File | Change |
| -- | -- |
| `apps/mobile/package.json` | `expo-apple-authentication`, `expo-crypto` via `expo install` |
| `apps/mobile/app.json` | `expo-apple-authentication` added to `plugins` |
| `apps/mobile/lib/auth-storage.ts` | new — Keychain read/write/clear for the token pair |
| `apps/mobile/lib/apple-sign-in.ts` | new — nonce, digest, `signInAsync`, credential shaping |
| `apps/mobile/app/(auth)/login.tsx` | replaces the placeholder with 9a and 9c |
| `apps/mobile/__tests__/apple-sign-in.test.ts` | new — 8 cases on the helper |
| `apps/mobile/__tests__/login.test.tsx` | new — 8 cases on the screen |
| `apps/mobile/__tests__/smoke.test.tsx` | deleted |

## Approach

### The nonce, which is the one thing worth reading twice

MAC-26 settled this and doc 04 repeats it, because getting it backwards produces
a 401 that looks exactly like a server bug.

```
raw = 32 random bytes as lowercase hex
digest = SHA256(raw), lowercase hex          → goes to Apple
raw                                          → goes to our API
```

Apple hashes **nothing** in the native flow. It copies the string it is given
into the `nonce` claim verbatim. The server hashes the raw value we post and
compares. Apple's *web* flow echoes a raw nonce, which is where the confusion
comes from and why Supabase and better-auth both carry open issues for it.

Hex on both ends because `expo-crypto`'s `digestStringAsync` defaults to hex. The
API's `test_raw_nonce_in_the_claim_is_rejected` exists to catch this client
getting it wrong, and `apple-sign-in.test.ts` asserts both halves so it fails
here first, with a readable message.

### One component, two screens

9a and 9c live in one file driven by a `Phase` state machine, not two routes. A
route push mid-sign-in puts a stack animation between the tap and Apple's sheet,
and a back gesture partway through a token exchange has no sensible meaning.

`verifying` and `storing` are separate phases because they are separately
visible. Each drives one of 9c's three lines.

### 9c is three named lines, and they are honest

Doc 26 is explicit that a spinner is the wrong answer, because a frozen view
during a slow call reads as a crash. The three lines are:

1. Confirming it's you with Apple
2. Checking your Apple token
3. Saving your session to the Keychain

Each advances off actual progress — Apple returning, the mutation resolving, the
Keychain write finishing — never a timer. A timed animation would let the screen
claim to be further along than it is, which is the same lie as the spinner with
extra steps.

### Failure states

- **Sheet dismissed** → back to 9a, no error. Cancelling is a decision, not a
  failure; an error message there blames the user for what they just chose.
  `AppleSignInCancelled` exists so the screen can tell the two apart, since Apple
  signals it with a `code` on a plain `Error` rather than a typed class
- **Anything else** → 9a with a recoverable message and the button still present.
  The copy says *nothing was created*, because the most likely worry after a
  failed sign-in is a half-made account
- **No identity token** → `AppleSignInMissingToken`. Apple can authorize and
  still return null; posting that is a 400 arriving from a state the user
  believes succeeded
- **Apple auth unavailable** → `isAvailableAsync` gates the button, so Android
  and older iOS get a sentence instead of a native throw at tap time

### Token storage

`expo-secure-store`, already installed and already in `plugins`. Keychain-backed,
so encrypted at rest. AsyncStorage is a plaintext file readable from a backup,
and a refresh token is a long-lived credential.

The two writes are sequential rather than `Promise.all`. Neither ordering is
atomic, but this one fails toward an access token with no refresh token beside
it, never the reverse. MAC-31 reads the pair, and a lone refresh token is the
state it cannot interpret.

## Alternatives rejected

**A hand-rolled button.** Apple's Human Interface Guidelines require the system
button for Sign in with Apple. A lookalike is an App Store rejection later for no
gain now, so `AppleAuthenticationButton` it is. The cost is that the button is a
native view, which the screen test mocks.

**A separate route for 9c.** See above — an animation between tap and sheet, and
a meaningless back gesture.

**Storing the whole `Session` object.** The response also carries `user` and
`created`. Neither belongs in the Keychain: `user` is server state React Query
should own, and `created` is a one-shot signal MAC-31 reads from the mutation
result, not from storage.

**Routing to Today on success.** Explicitly out of scope. Wiring the session gate
here merges two PRs into one large one.

## Django / React Native concepts in play

**Config plugins.** `expo-apple-authentication` needs an iOS entitlement, which
is a native project file the managed workflow does not check in. The plugin entry
in `app.json` is a build-time code generator: `expo prebuild` runs it and it
writes the entitlement. This is the general pattern for native config in managed
Expo — you declare the intent in `app.json` and the plugin owns the native edit.
It is the wrong choice when you need native code no plugin exists for; then you
eject and own the `ios/` directory forever.

**Mocking at the module seam.** Both test files mock at the import boundary —
the generated hook, the native modules, the two lib helpers — rather than
mocking `fetch` or rendering the real native view. Same pattern as
`index.test.tsx`. It is the right choice when the boundary is stable and typed,
which a generated client is by construction. It is the wrong choice when the
boundary is the thing most likely to be wrong; then you want an integration test
against the real thing.

**Hoisted `jest.mock` factories.** The factory cannot close over module-scope
imports, because jest hoists it above them. The Apple button mock therefore
declares `jest.fn()` in the factory and supplies the implementation in
`beforeEach`, where `Text` is in scope. The `require()` workaround is the common
alternative and this repo's lint config forbids it.

## Blast radius

Small. Two new lib modules nothing else imports yet, one screen that replaced a
placeholder, two new dependencies. No API change, so no schema regeneration and
nothing for the `api-client-drift` job to catch.

`__tests__/smoke.test.tsx` is deleted rather than updated: it asserted the
placeholder copy this ticket removes, and its stated purpose — proving Jest and
RNTL can render a screen — is now covered eight times over by `login.test.tsx`.

## Deliberately unhandled

- **Routing after success.** MAC-31. The screen sits on a completed 9c
- **Refreshing an expired access token.** MAC-31
- **Android.** The app is iOS-only for now; the availability check degrades
  gracefully rather than pretending otherwise
- **`created`** from the response. MAC-31 uses it to tell a first run from a
  returning user
- **Revocation.** `AppleAuthentication.addRevokeListener` exists and matters
  eventually, but nothing consumes a session yet

## Open questions

**Should the disclosure line be a link?** Doc 26 wants the dimmest text on the
screen and nothing more, so it is plain text. Once a privacy policy exists it
probably wants to point at it.

**The Verifying screen has no timeout.** A hung request leaves three lines and no
exit. The right fix is a global timeout in `customFetch`, which is MAC-31's
territory rather than a per-screen timer here.
