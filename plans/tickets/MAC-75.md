# MAC-75 implementation plan

## User outcome

A user who photographs a scene with no food or drink receives a specific message. The user can
retry or use Manual. A zero-calorie drink remains a valid food-analysis result.

## Files touched

- `apps/api/ai/provider.py`: add the explicit provider flag, permit an empty provider item list,
  and tell the model when to use the flag.
- `apps/api/ai/exceptions.py`: define the no-food domain exception.
- `apps/api/ai/services.py`: branch on the provider flag and record the billable outcome.
- `apps/api/ai/views.py`: map the domain exception to a typed HTTP response.
- `apps/api/ai/tests/`: cover the provider schema, service branches, quota accounting, and endpoint
  response.
- `packages/api-client/`: regenerate the OpenAPI document and TypeScript client.
- `apps/mobile/app/(app)/photo.tsx`: display the reviewed no-food detail and keep the Manual action.
- `apps/mobile/__tests__/photo.test.tsx`: cover the new mobile error state and retained input.
- `plans/tickets/MAC-75.md`: record this approved plan.

## Approach

Add `no_food_visible: bool` to `ProviderFoodAnalysis`. Remove the provider schema's one-item
minimum. Keep its 30-item maximum. Update the system prompt with two explicit rules. The model sets
the flag to `true` only when the image shows no food or drink. The model sets it to `false` for any
visible food or drink, including a zero-calorie drink.

Branch on the flag in `create_food_analysis` before local result validation. A true value records a
billable failed call with category `no_food_visible`. The record keeps the structured provider
payload, request identifier, token usage, and estimated cost. The service then raises a domain
exception. A false value continues through the existing item rounding and serializer validation.
An empty list with a false value remains invalid model output.
A contradictory result that reports no visible food and also returns items is invalid model output.
Its failure record keeps the provider payload, request identifier, token usage, and estimated cost.
It uses a distinct failure message so operators can count contradictions without payload inspection.
The service maps all known invalid provider payloads to the same typed API error path.

The view maps the domain exception to status 422 with code
`food_analysis_no_food_visible`. The detail says, "No food or drink was visible. Try another
photo." The request is valid, but its content cannot produce the requested analysis resource. The
endpoint does not create a successful analysis that the user could review or save.

The mobile screen adds this exact status and code pair to its safe display allowlist. It shows the
API detail and appends, "Manual entry is still available." Unknown status and code pairs continue
to use the generic message. The selected photo and description remain available for retry.

The provider call counts against the rolling quota. The provider completed paid work before it
reported the scene contents. Recording the row as a failed analysis prevents the entry service
from treating it as a saveable result.

## Alternatives rejected

- **Infer no food from zero macros.** A diet soda, black coffee, tea, or water can have the same
  macros as a blank scene.
- **Treat every empty list as no food.** An empty list with `no_food_visible=False` is invalid
  structured output. The explicit flag decides the branch.
- **Trust either half of a contradictory result.** A true flag with returned items gives no safe
  basis to discard or accept the analysis. Record invalid model output instead.
- **Return status 200 with an empty analysis.** There is no usable resource to review or save. This
  shape would force a second success type into the client.
- **Return status 502.** The provider answered correctly. The photo content, not the upstream
  service, prevents analysis.
- **Show every status 422 detail.** Authentication and framework responses can carry unreviewed
  text. The exact status and code allowlist fails safe.
- **Do not debit quota.** The provider call used tokens and incurred cost.
- **Add a new database status.** The existing failed status plus a specific failure category keeps
  the result unsaveable without a migration.

## Django and React Native concepts

**Explicit signal over inference.** A validator can test only facts that the data carries. The new
boolean carries the fact that macro values cannot answer.

**Domain exception.** The service names the business outcome. The view chooses its HTTP status and
public response shape.

**Provider boundary.** The external structured-output schema can contain fields that the successful
public API does not expose. The service translates between those shapes.

**Fail-safe allowlist.** The mobile app displays only reviewed status and code pairs. A new code
uses generic copy until the app accepts it.

## Blast radius

This change updates the provider schema and prompt, analysis service, API error contract, generated
client, and one mobile error state. It adds no database migration. It does not change saved entry
validation or the successful analysis response.

This change adds a user-visible error state. The pull request needs a live screenshot of that
state. Any temporary review harness stays uncommitted and is removed before final checks.

## Deliberately unhandled

- Confidence scores and per-item quality signals.
- General error handling on other screens.
- Automatic retry or re-analysis.
- Changes to the successful analysis payload.
- Broader model-quality judgments.

## Verification

- Test the provider schema and instructions.
- Test the true branch, false branch, false branch with an empty list, contradictory output, quota
  debit, and retained provider diagnostics.
- Test the typed status 422 and invalid-output status 502 endpoint responses.
- Keep the zero-calorie serializer regression test green.
- Test the mobile message, Manual hint, safe log, and retained photo and description.
- Regenerate the API client and run the drift check.
- Run `pnpm pre-pr`.
- Capture the no-food state in a live app for pull-request review.
- Compare a blank scene with a zero-calorie drink on a physical device when live provider
  acceptance is available. Mocks cannot prove model behavior.

## Open questions, answered

Return status 422. The endpoint receives a valid request, but the photo cannot produce an analysis
resource.

Count the call against rolling quota. The provider completed paid work before it reported that no
food or drink was visible.
