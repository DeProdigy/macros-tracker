# 10 — Feature: Apple Health (write-only)

## Scope

**Write-only.** The app writes logged nutrition to Apple Health. It does not read weight, activity, or anything else.

This is deliberate and worth keeping: one-directional flow means no sync conflicts, no reconciliation logic, no "which side wins when both edited." The Django backend stays the sole source of truth for food entries; HealthKit is a downstream mirror.

Reading weight and active energy is parked. See "Deferred" below.

## What gets written

Per `FoodEntry`, three HealthKit sample types:

| Macro | HealthKit identifier | Unit |
| -- | -- | -- |
| Calories | `dietaryEnergyConsumed` | kcal |
| Protein | `dietaryProtein` | grams |
| Fiber | `dietaryFiber` | grams |

Each sample is written with the entry's `eaten_at` timestamp so Health's own daily grouping lines up with the app's.

Note that HealthKit has no concept of a "food entry" — it stores independent quantity samples. Three samples per entry, correlated by timestamp.

## Permissions

* **Write-only authorization.** Request only share permission for these three types. Do not request read permission for anything, including the types being written
* Purpose string in `Info.plist` (`NSHealthShareUsageDescription` / `NSHealthUpdateUsageDescription`) explaining plainly what's written and why
* **HealthKit deliberately does not tell you whether write permission was granted.** Apple designed it this way so apps can't infer what a user declined. Writes to a denied type fail silently. Design for that: never gate app behavior on believing the write succeeded
* Ask for permission at a moment that makes sense — after the first entry is saved, not on first launch. A cold permission prompt gets denied

## Sync design

Writing happens **client-side only.** The Django backend never touches HealthKit — it can't; HealthKit is device-local by design and data never leaves the phone through this path.

Flow:

1. Entry saves successfully to the API
2. Client writes the three samples to HealthKit
3. Failure to write is logged locally, not surfaced as an error — the entry saved fine, which is what matters

Deletion: deleting a `FoodEntry` should delete the corresponding HealthKit samples. Store the HealthKit sample UUIDs locally against the entry ID so they can be found. Without this, deleted meals linger in Health forever and the user's Health data quietly diverges from the app's.

Editing an entry: delete the old samples, write new ones. Simpler than trying to mutate in place.

## Backfill

Users will have entries logged before they grant permission, or before this feature ships. A one-time "sync past entries to Health" action in settings handles it. Worth having; it's the difference between a feature that works and a feature that works from today onward.

Batch the writes. Writing hundreds of samples one at a time is slow.

## App Store considerations

HealthKit raises review scrutiny meaningfully:

* Purpose strings must be specific. Generic text gets rejected
* **Health data must not be used for advertising or sold**, and the privacy policy must say so
* HealthKit entitlement required in the provisioning profile — an EAS config change, not just a code change
* Apple may ask what the app does with Health data during review. "Writes nutrition the user logged, reads nothing" is a clean, easy answer — another argument for staying write-only

Since data never leaves the device on this path, the privacy story is genuinely simple. Keep it that way.

## Technical notes

* Requires a **development or production build**, not Expo Go. Already true after MAC-20
* `expo-health-kit` or a community HealthKit module; check current maintenance status before committing, since this space churns
* Config plugin needed for the entitlement and purpose strings
* iOS only. Android's equivalent (Health Connect) is a separate effort and out of scope while the app is iOS-only
* **Simulator HealthKit support is limited.** Test on device

## What you'd be learning

* Native module integration and Expo config plugins — the first time this project touches iOS platform APIs directly
* Permission models where the system deliberately withholds grant status
* Local-first data mirroring, and reconciling deletes across two stores
* App Store review requirements for a sensitive data category

## Deferred — reading from Health

Explicitly out of scope, recorded so the reasoning survives:

* **Weight** — would enable automatic progress tracking against a cut. Needs a weight model regardless, which should probably be built with manual entry first and HealthKit as an import path later
* **Active energy** — would enable dynamic calorie targets on training vs rest days. Genuinely interesting, and it interacts with `TargetVersion` in a non-trivial way (does a target version change daily? Or does the day carry an adjustment on top of the version?). That question needs answering before any code

Both are additive later. Neither changes anything being built now.
