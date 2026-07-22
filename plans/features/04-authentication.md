# 04 — Feature: Authentication

## Scope

Public App Store release means auth cannot be cut down. Required in v1:

* Email + password registration and login
* Email verification
* Password reset
* **Sign in with Apple**
* Account deletion (in-app)
* Token refresh and rotation

## Why Sign in with Apple is not optional

Apple's App Review Guideline 4.8: if an app offers any third-party or social login, it must also offer an equivalent privacy-preserving option, and Sign in with Apple qualifies. Beyond compliance, iOS users expect it, and it removes password friction entirely.

Implementation note: Apple returns the user's name and email **only on first authorization**. If you don't persist it then, you never get it again — a classic first-time-integrator bug. Store `apple_user_id` (the stable subject claim) as the join key, never the email, since users may relay a private address.

## Token strategy

**JWT with refresh rotation**, via `djangorestframework-simplejwt`.

* Access token: short-lived (~15 min)
* Refresh token: long-lived (~30 days), **rotated on every use**, old one blacklisted
* Both stored in `expo-secure-store` — Keychain-backed. Never `AsyncStorage`, which is plaintext on disk

Why rotation: a stolen refresh token is only useful until the legitimate client next refreshes, at which point the theft becomes detectable (reuse of a blacklisted token).

**The alternative worth understanding:** session cookies are simpler and safer for browsers, but awkward for native clients and cross-domain API calls. JWT is the right call here — but be able to articulate *why*, since this is a standard system design interview question.

## Endpoints

```
POST   /api/auth/register/            email, password → user, tokens
POST   /api/auth/login/               email, password → tokens
POST   /api/auth/refresh/             refresh → new access + new refresh
POST   /api/auth/logout/              blacklist current refresh
POST   /api/auth/verify-email/        token → confirm
POST   /api/auth/resend-verification/
POST   /api/auth/password-reset/      email → sends link
POST   /api/auth/password-reset/confirm/  token, new password
POST   /api/auth/apple/               identity token → tokens
DELETE /api/auth/account/             soft delete + purge schedule
GET    /api/auth/me/                  current user
```

## Account deletion

Both stores now require an in-app deletion path. Design:

1. `deleted_at` set immediately, all tokens blacklisted, user can no longer authenticate
2. Photos in R2 queued for deletion
3. Hard purge after a grace period (30 days), giving a recovery window for accidental deletion

Soft delete first is the right instinct — irreversible destruction on a single tap is a bad user experience and a bad support story.

## Email delivery

Transactional email for verification and reset. Options: Resend, Postmark, SES. Pick one, wrap it behind a thin interface in the `accounts` app so it can be swapped and so tests never send real mail.

Local dev: Django's console email backend. No third-party account needed to develop the flow.

## Mobile flow

```
Launch
  → token in secure store?
      no  → Welcome (Sign in with Apple | email login | register)
      yes → valid? → onboarding complete?
                        no  → Onboarding
                        yes → Home
```

Key implementation detail: **a global 401 handler** that attempts a token refresh once, retries the request, and on failure clears storage and routes to Welcome. Wire this into the React Query client so every generated hook inherits it — doing it per-call is how apps end up with inconsistent logout behavior.

## What you're learning here

* Django custom user models and why they must exist before the first migration
* Token-based auth mechanics, rotation, and the threat model behind it
* OAuth-ish identity token verification (Apple's JWKS, signature validation, audience checks)
* Secure credential storage on device
* React Query's interceptor and cache-invalidation patterns for auth state

## Security requirements

* Rate limit login, register, password reset, and Apple auth by IP and by email
* Never leak whether an email exists — password reset returns the same response either way
* Verify Apple's identity token signature against their JWKS endpoint, and check `aud` and `iss`. Do not trust a client-supplied token unverified
* Password validators enabled; no arbitrary minimums below Django's defaults
