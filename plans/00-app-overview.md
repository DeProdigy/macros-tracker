# 00 — App Overview

## What it is

A photo-based macro tracker. Snap or upload a photo of food, add a short description, AI estimates calories / protein / fiber, and the entry persists against your daily targets. The home screen shows progress toward those targets, a streak counter, and an on-demand "what should I eat" suggestion.

The core problem it solves: logging food accurately is tedious enough that people stop doing it. A photo plus a sentence is low enough friction to sustain daily.

## Why this project exists

This is a **learning project** first and a product second. Goals, in priority order:

1. Level up React Native (Expo) — navigation, state, camera/media, forms, offline-ish behavior
2. Level up Django — DRF, auth, modeling, background work, testing
3. Learn production deployment and resource management end to end
4. Learn the App Store release pipeline

Secondary goal: it should be genuinely usable daily by the author, because a tool you don't use is a tool you stop building.

## Stack

| Layer | Choice |
| -- | -- |
| Backend | Django + Django REST Framework |
| Database | PostgreSQL |
| Mobile | Expo (managed workflow), React Native, TypeScript |
| API contract | drf-spectacular → `openapi.json` → Orval → React Query hooks |
| Monorepo | Turborepo |
| AI | OpenAI (vision for photo analysis, chat for targets + advice) |
| Object storage | Cloudflare R2 (S3-compatible, no egress fees) |
| Hosting | Railway (Django + Postgres), auto-deploy on merge to main |
| CI | GitHub Actions |
| Ship | EAS Build + EAS Submit → TestFlight → App Store |

## Feature set (v1)

* **Auth** — email/password, email verification, password reset, Sign in with Apple, account deletion
* **Onboarding** — question flow that produces personalized daily targets via an AI call, with server-side sanity bounds
* **Targets** — calories, protein, fiber. Versioned, adjustable at any time
* **Food logging** — camera or photo library, client-side compression, upload, AI macro estimate, correction before save
* **Dashboard** — today's totals vs targets, progress graph, day-by-day history navigation
* **Streaks** — consecutive days with at least one logged entry
* **Advice** — on-demand button: "given what's left in my budget, what should I eat?"

## Explicitly out of scope for v1

Parked in the v2 backlog, deliberately:

* Saved foods / quick-add for label-exact staples (protein shakes, egg whites)
* Multi-photo meals and per-food line items
* Background/proactive advice generation
* Android release
* Web app (TanStack Start) — the typed api-client package keeps this cheap to add later
* Social features of any kind

## Core product decisions

**One photo = one entry with total macros.** No per-food line items. Simpler model, simpler UI, and corrections happen at the entry level. Revisit only if real usage proves it insufficient.

**Streak = logged at least one entry that day.** Consistency-based, like Whoop's streak for wearing the band — not achievement-based. Missing your protein target should not punish you for showing up.

**Advice is on-demand, behind a button.** Every AI call costs money; background generation for every user every day does not pay for itself in v1.

**Targets are versioned, never updated in place.** Historical days stay accurate against the targets that were active at the time.

## Definition of done for v1

A TestFlight build that the author and a handful of friends use daily for two weeks without the author needing to touch the database manually.
