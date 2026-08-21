# MAC-31 — Mobile: session gate and the global 401 handler

Approved 21 Aug 2026. Linear:
[MAC-31](https://linear.app/hintology/issue/MAC-31/mobile-session-gate-and-the-global-401-handler).

## Context

Closes E2. MAC-30 ended with two tokens in the Keychain and nothing consuming
them. This makes the session survive a relaunch, refresh silently when the
access token expires, and end cleanly on logout or deletion.

The interesting part is one variable.

## The bug this exists to prevent

MAC-25 turns on `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION`. Both
correct.

Three React Query hooks mount on Today at once behind an expired access token.
All three 401. A naive handler fires three refreshes with the same refresh
token. The first rotates it and blacklists the original. The second and third
present a blacklisted token, fail, and the handler logs the user out.

Correct auth code plus correct security settings produce a logout bug. It shows
up only under concurrency, so it will never appear while testing one screen and
will appear constantly on a real dashboard.

The fix is one shared promise, and
`__tests__/http-client.test.ts` proves it: deleting the three lines that return
the in-flight promise turns two of those tests red and leaves the other thirteen
green.

## Where the code lives, and why

`customFetch` is the choke point, as the ticket says. But
`packages/api-client` cannot import `expo-secure-store` without becoming
Expo-only, and it cannot import the generated `refreshSession` at all — every
generated operation imports `customFetch` from that same file, so it is a cycle.

So the package takes a `SessionBridge` from the app:

| Owner | Owns |
| -- | -- |
| `packages/api-client/http-client.ts` | the policy: one refresh, shared by all waiters, then one retry, and never on a public path |
| `apps/mobile/lib/api-auth.ts` | the bindings: which store, which endpoint, what "give up" means |

`configureSession(null)` restores the pre-MAC-31 behaviour exactly, which is what
keeps the package usable from a test or a script with no Keychain under it.

`publicPaths` is built from `getCreateSessionUrl()` and `getRefreshSessionUrl()`
rather than written out, so a route rename cannot leave the list stale. It covers
both halves of the ticket's warning: a 401 from sign-in must not trigger a
refresh, and refresh cannot refresh itself.

## Files touched

| File | Change |
| -- | -- |
| `packages/api-client/http-client.ts` | token attachment, single-flight refresh, one retry, the deadline, `ApiTimeout` |
| `packages/api-client/index.ts` | exports `configureSession`, `ApiTimeout`, `SessionBridge` |
| `apps/mobile/lib/api-auth.ts` | new — the bridge implementation |
| `apps/mobile/lib/session.tsx` | new — `SessionProvider`, `useSession`, sign-out, delete |
| `apps/mobile/lib/palette.ts` | new — the colours the four E2 screens share |
| `apps/mobile/lib/auth-storage.ts` | `getAccessToken` and `getRefreshToken` for reading one half |
| `apps/mobile/app/_layout.tsx` | holds the splash open, wraps in `SessionProvider` |
| `apps/mobile/app/index.tsx` | was the health screen, is now the launch gate |
| `apps/mobile/app/onboarding.tsx` | new — the gate's third outcome, standing in for E3 |
| `apps/mobile/app/(app)/_layout.tsx` | new — one redirect guarding every signed-in route |
| `apps/mobile/app/(app)/today.tsx` | new — the placeholder shell |
| `apps/mobile/app/(app)/settings.tsx` | new — sign out, delete account |
| `apps/mobile/app/(app)/health.tsx` | the old home screen, moved and linked from Settings |
| `apps/mobile/app/(auth)/login.tsx` | adopts the user, then redirects |
| `apps/mobile/__tests__/` | five new suites, `index.test.tsx` renamed to `health.test.tsx` |

No API change, so no schema regeneration and nothing for `api-client-drift`.

## Approach

### Routing from state, not from calls

Screens render a `<Redirect>` based on what `useSession()` says. Nothing calls
`router.replace` to log someone out.

This matters most for the thing that has no component to navigate from. When a
refresh fails, `customFetch` calls `onSessionExpired`, which moves the session
state, and every guarded route follows on the next render. The imperative
version needs every future caller to remember to navigate, and the 401 handler
cannot participate at all.

`app/(app)/_layout.tsx` is one guard covering every signed-in screen, including
screens written months from now that never thought about auth.

### The gate has three outcomes

```
token in secure store?
  no  → Welcome
  yes → valid? → onboarding complete?
                   no  → onboarding
                   yes → Today
```

Not two, because doc 26 made the onboarding stack exitable and a user with
entries and no targets is now a coherent state. A stored token is also not a
session: it can be expired, blacklisted, or attached to a deleted account, and
only `GET /api/users/me/` knows which.

The splash stays up for the whole question. `SplashScreen.hideAsync` runs from
an effect in the gate, only once the answer exists. Hiding earlier shows a
returning user a flash of Welcome, which reads as having been logged out.

### `created` is not consulted

The sign-in response carries it, and routing ignores it. A returning user who
never finished onboarding belongs in the same place as a brand-new one, and the
server already tracks that in `onboarding_completed`. Branching on both would be
two sources for one decision.

### Sign-out drops the tokens whether or not the server answers

`DELETE /api/auth/sessions/current/` is best-effort and its failure is swallowed.
Sign-out that depends on a reachable server is sign-out that fails on a train.

Delete account is the opposite, and deliberately so. A 401 means the account is
already deactivated, which the API documents, so that counts as done. Anything
else keeps the session and shows an error, because signing someone out of an
account that still exists tells them the deletion worked.

Both clear the React Query cache. Otherwise the next user on the device sees the
previous user's data until every query refetches.

## The timeout, and the hole in it

`customFetch` now abandons an attempt after 15 seconds and throws `ApiTimeout`.
MAC-30's plan flagged this as MAC-31's territory, because the Verifying screen
had no exit from a hung request.

Three things made it bigger than it looked:

- `AbortSignal.timeout` and `AbortSignal.any` are not safe to assume on Hermes,
  so the controller is hand-rolled
- React Query passes its own cancellation signal into every generated operation.
  Replacing `options.signal` would break query cancellation silently, so the two
  signals are composed and only our own timer becomes an `ApiTimeout`
- The retry gets a fresh deadline. Reusing one would hand attempt two a clock
  that has already run down

**The refresh call is exempt, and this is the uncomfortable part.** Aborting a
refresh does not cancel it. The server may already have rotated the token and
blacklisted the copy still in the Keychain, and we would be discarding the only
copy of its replacement — the exact self-inflicted logout the rest of this ticket
prevents. iOS's own request timeout, around 60 seconds, is the backstop instead.
A hung refresh therefore hangs its waiters for that long.

That is a real gap, not a solved problem. The honest fix is server-side
idempotency on refresh, or a client that can tell "no response" from "response
lost", and neither belongs in this ticket.

## Alternatives rejected

**Auth logic in the mobile app, wrapping the client.** The ticket rules it out
and it is right to: a wrapper is only the choke point until someone imports a
generated hook directly, and nothing stops them.

**`expo-secure-store` as a dependency of `packages/api-client`.** Makes a package
whose whole point is being a typed contract into an Expo-only package. The next
consumer — a script, a web client, a test — inherits a native module it cannot
load.

**Importing `refreshSession` into `http-client.ts`.** A cycle. Every generated
operation imports `customFetch` from there. ES modules tolerate it when the use
is deferred to runtime, which is exactly the kind of thing that works until a
bundler changes evaluation order.

**A subscriber list for session expiry.** There is one session, so a second
listener would mean two things believe they own routing to Welcome. A single
slot makes that impossible rather than unlikely.

**`Alert.alert` for the delete confirmation.** A native modal is harder to test
and cannot carry doc 16's timeline copy, which is the part that matters. An
inline panel can.

## Django / React Native concepts in play

**Dependency injection across a package boundary.** The general shape: the lower
package defines an interface for what it needs, and the higher one supplies it.
It keeps the dependency graph acyclic and the lower package portable. It is the
wrong choice when there is only ever going to be one implementation and the
indirection buys nothing — the cost here is that reading the 401 path means
opening two files.

**Single-flight, sometimes called request coalescing.** N callers want one
expensive or non-idempotent thing; the first starts it and the rest await the
same promise. Same pattern as a cache stampede lock or Django's
`get_or_create`. It is wrong wherever the operation is genuinely per-caller —
coalescing two different users' requests would be a data leak.

**Routing from state.** expo-router's model, and React Router's, and SwiftUI's.
Declare where you should be given the current state; let the framework move you.
The imperative alternative is fine in small apps and rots the moment two
different code paths can log someone out.

**Splash as a state.** `preventAutoHideAsync` at module scope, `hideAsync` when
the app knows what to draw. Standard for any launch that has to ask a question
before it can render.

## Blast radius

`customFetch` is on the path of every request in the app, so a bug here is a bug
everywhere. That is the point of the ticket and also the risk of it. The
mitigation is that the new behaviour is inert without a bridge, and 15 tests
drive the real function with `fetch` as the seam rather than mocking the layer
under test.

Everything else is additive: four new routes, three new lib modules, one screen
moved.

## Deliberately unhandled

- **Real onboarding.** `app/onboarding.tsx` is a placeholder with an exit. E3
  replaces it with 9d, 9e and 9f
- **Real Today.** No rings, no tiles, no entry list. E4 and E5 own those, and
  doc 16 already decided the first-run state is a variant of the home screen
  rather than a screen of its own
- **Real Settings.** Doc 16's six groups, target history, AI usage, the Apple
  Health toggle. What is here is the two things deletion needs to be testable
- **A hung refresh.** See above
- **Apple revocation.** `addRevokeListener` still has nothing consuming it
- **Android.** Still iOS-only

## Open questions

**Should the launch gate distinguish "server unreachable" from "signed out"?**
Right now a failed `GET /api/users/me/` at launch clears the tokens and sends
the user to Welcome, whatever the cause. On a plane that is a wrongful logout,
and the tokens might have been fine. Branching on `ApiTimeout` and network
failure — keeping the session and showing a retry — would be more correct and
adds a fourth state to the gate. Worth deciding before E4 makes launches
frequent.

**Should the health screen exist at all?** It survives here because it is the
fastest way to tell "the app is broken" from "the API is down" on a device
build, and that question came up during MAC-30. It is also a diagnostics screen
in a consumer app. Doc 16 does not mention it.

## Device checklist for E2

Not verified on hardware in this PR. The Apple Developer membership needed for
a build is still the blocker MAC-30 recorded.

1. Fresh install, sign in, land on the Today shell
2. Force-quit and relaunch: still signed in, no second Face ID prompt
3. Shorten `ACCESS_TOKEN_LIFETIME` locally, confirm a request refreshes with no
   visible interruption
4. Fire several concurrent requests against an expired access token: one
   refresh, no logout
5. Log out, confirm the refresh token is blacklisted
6. Delete the account, sign in again with the same Apple ID, confirm the same
   user comes back rather than a duplicate
