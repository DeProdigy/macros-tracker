# MAC-50: the manual target editor, and the app's front door

Approved 30 Aug 2026. Linear:
[MAC-50](https://linear.app/hintology/issue/MAC-50/mobile-the-adjust-screen-and-the-settings-target-editor-6h).

## Slice and exception

**Slice 1 of 3**, which ends on: *a user can now set their own calorie, protein,
and fiber targets by hand and change them later.*

It ships a screen, so it claims no Gate 0 exception. It is also what finishes the
slice: MAC-38, MAC-39, MAC-40, MAC-53 and MAC-47 all built the machinery behind
this one form.

## Why it was Urgent

MAC-47 made onboarding a hard gate and removed the placeholder's *Not now*. The
six questions do not exist yet, so between that merge and this one **a new user
could not get into the app at all**.

This screen is the way through the gate. Saving a target writes the user's first
`TargetVersion`, which is what sets `onboarding_completed` and opens Today. Same
component, same write, whether it is reached from onboarding or from Settings
later.

## The routing trap, avoided by one directory

`app/targets.tsx` sits **outside** the `(app)` group, next to `onboarding.tsx`,
and carries its own signed-out check.

Inside `(app)` it would have been hidden from every user who needs it. That guard
redirects anyone without targets, and this is the screen where a user gets their
first ones.

This is the second time in two tickets. MAC-47's review found the same shape:
closing the deep-link hole hid `settings.tsx`, and with it the only sign-out and
account-deletion path, from every un-onboarded user.

**A route group guard hides everything in the group, including the screens that
are the way out of the state being guarded.** Worth a habit rather than a note:
before adding a redirect, list what else lives behind it.

## No orange warning, and that is a decision

Doc 15 wants the row to turn orange live, while the user is still stepping, when
a number sits outside the *suggested* range. It does not, and the reason is worth
writing down because the ticket asked for it.

**The client cannot compute that range.** It scales with body weight, the server
never sends it, and `TargetVersion` carries no bounds. Nothing has asked the user
for a weight until MAC-42, so in onboarding the server cannot compute it either.

Three options were on the table.

- **Copy the bands into TypeScript.** Instant feedback, no round trip. It also
  puts research numbers in two places that drift apart in silence, and MAC-53
  already paid for that once: the `Sex` enum is mirrored in two files and needed
  drift tests to stay honest. And it still could not warn in onboarding, because
  the weight is missing on both sides
- **Add `GET /api/targets/bounds/`.** One copy of the science, no drift. It costs
  a backend change and a `pnpm generate:api`, and it makes the app's front door
  wait on them
- **Ship without the warning.** Chosen

The absolute range still holds, which is the half that matters for harm. The
steppers clamp inside it and a 400 renders whatever gets past them. The warning
lands in slice 2, where MAC-42 has collected the weight it needs.

**Protein does not clamp client-side, deliberately.** Its absolute range scales
with weight on the server, and the client has no weight to scale by. MAC-40 ruled
that a missing weight skips the protein bound rather than refusing the write, so
a guessed clamp here would refuse values the server would have accepted.

`CALORIE_LIMITS` and `FIBER_LIMITS` mirror the two flat server constants. They
are a stepper convenience, not the guard.

## Every failing field, not the first

`reject_outside_absolute` reports all of them at once, and the screen shows all
of them. A caller who fixes one, resubmits, and is told about the next has been
made to guess twice, which is reasoning the server side already carries.

The generated type for a 400 is `data: void`, so the body shape is not typed.
`fieldErrorsFrom` reads it defensively and falls through to a plain message when
nothing recognisable comes back. Rendering `undefined` at a user is the failure
to avoid, and a test pins it.

## The round trip

Saving flips `onboarding_completed` on the server. The route guard reads the
session, not the network. So the screen refetches `GET /api/users/me/` and calls
`session.updateUser` before it redirects.

Without it the user saves targets and stays on this screen, which is the same
class of bug MAC-47 fixed one ticket ago.

`updateUser` is back on the session, having been added and then removed in
MAC-47 when the sequencing reversal deleted its only caller. It ships here with
the caller that needs it.

## Smaller calls worth naming

**A 404 from `current/` is the ordinary first-run answer**, not a failure. It
falls through to the starting point and tells the user nothing went wrong.

**The starting point is 2,000 / 140 / 30, labelled as a starting point.** The app
cannot recommend anything yet: Mifflin-St Jeor needs six answers and MAC-42 is
the ticket that asks for them. A number shown with no hedge reads as advice.

**`effective_from` uses the phone's local date**, via `toLocaleDateString("en-CA")`
for an ISO-shaped string. Someone in Auckland setting targets at 09:00 gets today,
not the server's yesterday.

**A stepper clears its own field error.** A stale message under a number the user
just changed reads as a fresh rejection of the new value.

**The Settings entry is a plain link.** Doc 16's `7c` row carries the three
current numbers plus `ADJUST` and `HISTORY`, and MAC-44 builds it. Shipping the
full row now would mean a `HISTORY` control that opens nothing.

## Files

`app/targets.tsx` (new), `app/onboarding.tsx`, `app/(app)/settings.tsx`,
`lib/session.tsx`, and two test files.

Mobile only. No API change, so `openapi.json` does not move and the drift job has
nothing to say.

**`.expo/types/router.d.ts` is generated and gitignored.** A new route makes the
local copy stale and `tsc` rejects `/targets`. Regenerated by running the dev
server rather than hand-edited. CI never has the file, so it type-checks against
the loose fallback and was never going to fail on this.

## Verification

Five mutations, each caught:

| Mutation | Result |
| --------------------------------------------- | ------------ |
| The save does not refetch the user | 1 test fails |
| Only the first failing field renders | 1 test fails |
| An unreadable 400 body renders nothing | 1 test fails |
| Calories step by 1 instead of 10 | 1 test fails |
| The onboarding link is removed | 1 test fails |

Gates: prettier, `pnpm lint`, `pnpm check-types`, 100 jest tests, 364 python
tests, `pnpm generate:api` clean.

## Deliberately unhandled

- **The live suggested-range warning.** Slice 2, with the weight
- **Doc 16's full `7c` targets row**, with the numbers and `HISTORY`. MAC-44
- **The six questions.** MAC-42 replaces the onboarding placeholder entirely
- **A back control on the editor.** From onboarding there is nowhere to go back
  to, and from Settings the platform gesture already works

## Open questions

- **Should the editor look different from onboarding and from Settings?** It is
  one component and doc 15 says to keep it that way. Reached from onboarding it
  is the last step of a flow; from Settings it is an edit. Neither says so on
  screen today
