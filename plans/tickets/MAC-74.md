# MAC-74 implementation plan

## User outcome

A user sees the API's actionable explanation when photo analysis fails. A developer can use the
stable error code to diagnose the failure.

## Files touched

- `apps/mobile/app/(app)/photo.tsx`: read structured analysis errors, show their detail, and log
  their code.
- `apps/mobile/__tests__/photo.test.tsx`: cover structured API errors, quota errors, and fallback
  errors.
- `plans/tickets/MAC-74.md`: record this approved plan.

## Approach

Add a small local helper that narrows `ApiError.body` from `unknown`. The helper accepts only a
non-empty string `detail` and a string `code`. It does not assume that every HTTP failure contains
JSON.

The analysis catch path first checks for `ApiError`. It logs the HTTP status for every API failure.
It logs the stable code when the body contains one. The log uses `null` when the body does not
contain a code, so code-less proxy and validation failures still have a consistent diagnostic
shape.

The screen keeps the current message for status 429. It shows the API detail only when status 502
uses `food_analysis_failed` or `food_analysis_invalid_output`. It appends the Manual entry hint to
that detail. It adds a period first when the API detail does not end with one. It uses the existing
generic message for every unknown code, unrelated HTTP status, network failure, unparsed response,
or malformed body.

The user sees the actionable detail but does not see the internal code. The log contains only the
HTTP status and code. It does not contain the response body, meal description, photo information,
or other user data.

## Alternatives rejected

- **Cast the body to `FoodAnalysisError`.** The HTTP layer can also return HTML, plain text, or
  malformed JSON. A generated success or error type cannot prove the runtime value.
- **Change the API or generated client.** The API already returns the required detail and code.
- **Add a shared error component.** No other screen needs this behavior in this ticket.
- **Add a released-build error reporter.** MAC-62 owns production observability.
- **Show the raw response or code to the user.** Internal data does not help the user choose the
  next action.
- **Show every 502 detail.** A new or unrelated code could contain text that nobody reviewed for
  this screen. The explicit code allowlist fails safe. An unknown code uses the generic message
  until the mobile app reviews and accepts its copy.

## Django and React Native concepts

**TypeScript narrowing at an untrusted boundary.** `ApiError.body` is `unknown` because an HTTP
failure can contain any payload. Runtime property checks make the two strings safe to use. A type
assertion would only hide the uncertainty from the compiler.

**Progressive error disclosure.** The user receives the explanation and next action that help on
the current screen. The developer receives the stable diagnostic code. Each audience gets the
smallest useful amount of information.

**Local component state.** The existing error state changes only the alert copy. The selected
photo and description remain in their current state, so the user can retry without repeating
input.

## Blast radius

Only photo-analysis failure handling changes. Upload, retry, quota, save, and navigation behavior
remain unchanged. There is no backend, schema, generated-client, dependency, or migration change.

This change updates a user-visible failure state. The pull request needs a live screenshot of that
state. Any temporary review harness stays uncommitted and is removed before final checks.

## Deliberately unhandled

- Released-build error reporting.
- Retry policy changes.
- Errors on other screens.
- New API error codes or API copy.
- MAC-75's no-food response.
- Offline behavior.

## Verification

- Run the focused photo-screen tests.
- Run mobile lint and type checking.
- Run `pnpm pre-pr`.
- Capture the changed failure state in a live app for pull-request review.

## Open questions, answered

Use `console.error` for the status and code in this ticket. This supports local and attached-device
diagnosis. MAC-62 adds released-build error reporting.

Show the API detail to the user. Do not show the machine-readable code.
