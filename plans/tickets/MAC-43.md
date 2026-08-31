# MAC-43: Complete target onboarding

## User outcome

A user can accept or adjust proposed targets, finish mandatory onboarding, and
arrive at the first-food prompt.

## Current behavior

The onboarding route collects six answers and returns a deterministic proposal.
The result cannot save or adjust the proposal. The separate target editor can
save a version, refresh the user, and handle server refusals.

## Files and layers

- `apps/mobile/app/onboarding.tsx`: add accept and adjust actions.
- `apps/mobile/app/targets.tsx`: seed onboarding edits from the proposal and
  return the saved user to the first-food prompt.
- `apps/mobile/app/first-food.tsx`: add the mandatory prompt. Keep its food
  action disabled until food logging exists.
- A small mobile module or route parameters: carry proposal values without
  copying save logic.
- Mobile tests: cover acceptance, adjustment, refusal, retry, session refresh,
  and route replacement.

The Django endpoint and generated API client already support the required
write. This ticket does not change either contract.

## Approach

The onboarding result sends proposal values to the existing target editor.
Direct acceptance uses the same save path as an adjusted proposal. The editor
creates a TargetVersion, then refetches the current user. It replaces the route
stack with the first-food prompt after the session reports onboarding complete.

The prompt has a disabled food action. This is honest about the current product
and prevents a skip to Today. MAC-55 enables the action when manual logging
exists.

## Alternatives rejected

- Do not duplicate target-save and error handling in onboarding.
- Do not navigate directly to Today. The canonical first-run flow requires the
  first-food prompt.
- Do not use navigation history to detect onboarding. Account state is the
  source of truth.
- Do not expand this ticket into food logging.

## Concepts

- Expo Router route replacement removes completed onboarding from Back.
- Server-derived session state opens the application only after a target write.
- One save path prevents acceptance and adjustment from handling errors
  differently.

## Blast radius

The change affects first-run onboarding and the onboarding entry to the target
editor. Settings target edits must keep their current values and return path.

## Deliberately unhandled

- Photo, Manual, and Recent food logging.
- Target history.
- AI target generation.
- Enabling the first-food action.

## Verification

- Targeted onboarding and target-editor tests.
- Full mobile Jest suite.
- Mobile TypeScript and ESLint.
- Prettier and diff checks.
- Live screenshots for the result, adjustment, refusal, and first-food states
  in the pull request.
