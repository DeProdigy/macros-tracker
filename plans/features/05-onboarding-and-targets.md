# 05 — Feature: Onboarding & Targets

## Purpose

New user answers a short set of questions; the app produces personalized daily targets for calories, protein, and fiber, with a plain-English explanation of the reasoning. Targets are adjustable forever after.

## Questions collected

| Field | Type | Notes |
| -- | -- | -- |
| Age | int |  |
| Biological sex | enum | Affects BMR meaningfully |
| Height | int (cm or in) |  |
| Current weight | decimal |  |
| Goal | enum | cut / maintain / gain |
| Goal weight | decimal | Skipped if maintaining |
| Timeline | enum | Aggressive / moderate / relaxed |
| Activity level outside training | enum | Sedentary → very active |
| Training days per week | int |  |
| Dietary constraints | free text | Optional. Feeds advice later too |

Collect all of it *before* the AI call. One request, not a conversation.

## The AI call, and an honest caveat

The decision was made to use an AI call for target generation. Worth stating the tradeoff explicitly, because it will come up again:

Mifflin-St Jeor plus an activity multiplier is a deterministic formula. It is free, instant, reproducible, and testable. An LLM doing that arithmetic is slower, costs money, and can produce a different answer for identical input.

What the LLM genuinely adds is judgment around the edges — protein targets relative to lean mass and goal, fiber recommendations, sensible rate-of-loss guidance, and a readable explanation of *why* these numbers.

**Recommended implementation** (satisfies the decision, keeps the value): send the formula's computed baseline in the prompt as context, and ask the model to adjust and explain. You get deterministic arithmetic plus AI judgment and rationale. If the model's numbers drift far from the baseline, that's a signal worth logging.

## Server-side guardrails — mandatory

Public app, health-adjacent numbers. The AI's output is **never** trusted directly:

* Calories: clamp to a floor and ceiling by sex and body weight. Reject anything implausibly low regardless of what the model says
* Protein: clamp to a sane g/kg range
* Fiber: clamp to a reasonable daily range
* If the response falls outside bounds, fall back to the deterministic formula and log it
* Validate the response shape strictly — request JSON, parse it, reject malformed output rather than pattern-matching prose

**Disclaimer required in the UI:** these are estimates, not medical advice. Non-negotiable for a health-adjacent public app, and Apple review will look for it.

## Endpoints

```
POST /api/onboarding/targets/    answers → proposed targets + rationale
POST /api/targets/               create a new TargetVersion (accept or manual)
GET  /api/targets/current/       latest version
GET  /api/targets/history/       all versions, for showing how goals evolved
```

Note that accepting onboarding targets and manually adjusting them both write a `TargetVersion` — same path, different `source` value.

## Adjusting targets later

* Editable at any time from settings
* Every change writes a **new** `TargetVersion`; nothing is updated in place
* `DailyLog` rows already created keep pointing at their original version
* A history view showing targets over time is a small feature that makes the versioning tangible — and is genuinely interesting on a long cut

## Mobile flow

Multi-step form, one question per screen. Progress indicator. Back navigation preserves answers.

Worth doing properly rather than as one long scroll — multi-step forms with validation and preserved state are a real RN skill, covering controlled inputs, per-step validation, and state that survives navigation.

Loading state during the AI call matters: it takes a few seconds, and a frozen screen reads as a crash.

Result screen shows the three numbers plus the rationale, with **Accept** and **Adjust** options. Never force acceptance of a generated number.

## What you're learning here

* Multi-step form state management in React Native
* Structured JSON output from an LLM, and validating it rather than trusting it
* Defensive design around AI output in a domain where wrong answers matter
* The slowly-changing-dimension pattern in practice
* When *not* to use an LLM — a judgment worth having explicit reasoning about
