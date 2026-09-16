# MAC-58: Today slice: finish calorie, protein, and fiber progress

Linear:
[MAC-58](https://linear.app/hintology/issue/MAC-58/today-slice-finish-calorie-protein-and-fiber-progress).

## User outcome

A user opens Today and sees at a glance what remains for calories, protein, and
fiber on the selected day.

## The backend already does its half

The ticket carries a `backend` label. No backend change is needed.

`day_data` in `apps/api/entries/serializers.py:232` already returns `targets` from
the day's captured `target_version`, and falls back to the current effective target
for a day with no log yet. `DaySerializer` already ships it, and the generated
client already types it as `DayTargets | null`.

Three of the five acceptance criteria are satisfied by that alone. Progress uses
the day's own target version. Current targets apply to a new empty day. An old day
does not change after a target edit, because the row captured its version when it
was written.

`apps/mobile/app/(app)/today.tsx` was throwing `day.targets` away and rendering
three bare numbers.

## Files touched

- `apps/mobile/lib/day-progress.ts` (new)
- `apps/mobile/components/calorie-ring.tsx` (new)
- `apps/mobile/components/macro-tile.tsx` (new)
- `apps/mobile/app/(app)/today.tsx`
- `apps/mobile/lib/palette.ts`
- `apps/mobile/__tests__/day-progress.test.ts` (new)
- `apps/mobile/__tests__/today.test.tsx`
- `apps/mobile/package.json` and the lockfile, for `react-native-svg`
- `plans/tickets/MAC-58.md`

## Approach

**The rules live in a pure module.** `lib/day-progress.ts` turns a `Day` into
consumed, target, remaining, fraction, and status per macro. It holds the product
decisions and nothing about rendering, because whether 191g of protein against a
185g target is a warning or a win is a decision that deserves a named test.

**The ring is SVG.** The over-target state draws two concentric arcs. Each arc is
a circle with a dash pattern, one dash as long as the fraction wanted and one gap
covering the rest, with the whole group rotated -90 degrees so a dash starts at
twelve o'clock rather than at three.

**The overage keeps the ring's scale.** The approved over-target screen draws the
overage as a second inner arc measured against the same target, so 310 over 2350
reads as 13 percent of a day and not as a second full lap. `caloriesOverFraction`
computes that and is tested directly, because it is the single idea most likely to
be lost in a later refactor.

**The tiles are a separate component from the ring.** They look related and mean
opposite things. Passing the calorie target is a warning. Passing the protein
target is the goal. One component with an `isCalories` flag would hide that
contradiction inside a branch.

## What the approved design says, and what is not mine

Read `design/source/linear-2026-08-31/19-today-normal.png` and
`20-today-over-target.png`.

Three elements appear in those mockups and are out of scope here:

- **"What should I eat?"** belongs to the Personal Dietician Advice follow-up
  milestone.
- **The "4 DAYS" chip** is a streak, which the ticket excludes.
- **"READING THE RING"** is annotation on the mockup explaining the design. It is
  not an element.

A careless read of an approved artifact ships all three. Naming them here is
cheaper than reverting them in review.

## Colours

`palette.ts` gained `card`, `ringTrack`, `calories`, `caloriesOver`, `protein`,
`proteinMet`, `fiber`, and `fiberMet`, in both themes.

These are the first entries in that file a mockup dictates rather than a developer
choosing. A comment says so, and says MAC-61 owns the real visual system and
should absorb them. Shipping the ring in the placeholder blue would contradict an
approved artifact for no gain.

## Regression tests

`__tests__/day-progress.test.ts` covers eight cases: under target, over target
scaled against the target, an overage capped at one lap, protein passing counted
as met, landing exactly on a target, a null target set, a zero target, and an
empty day.

`__tests__/today.test.tsx` gained four screen tests. Worth noting why they were
missing: every existing Today test used `targets: null`, so they all passed
against the new code without touching the ring at all. A green suite said nothing
about this feature until those four existed.

## Verification

1. All mobile tests pass, 212 across 24 suites.
2. `pnpm pre-pr` passes.
3. On the iPhone: the ring, both tiles, the over-target state, and a past day.
   This needs a new development build, because `react-native-svg` is native.

## Alternatives rejected

- **Draw the ring with rotated Views.** Two half circles per ring behind an
  `overflow: hidden` parent, no native dependency, no new build. It costs about
  eighty lines of geometry per ring, the inner overage arc is awkward, and MAC-61
  will restyle it anyway. Paying the native cost once while already in a build
  cycle is cheaper than owning that maths.
- **Substitute the current target when `targets` is null.** It would remove an
  empty state, and it would silently rewrite history for an old day. Capturing a
  `TargetVersion` per day exists to stop exactly that.
- **One progress component with a flag for calories.** See above. The two macros
  disagree about what "over" means.
- **Compute progress inside the screen.** The rules would then only be reachable
  through a render, and a product rule would have no test of its own.

## Concepts in play

- **Separate the rules from the rendering.** The test for "passing the protein
  target is a win" should not need a component tree. When a product rule has a
  name, give it a module.
- **An SVG arc is a dashed circle.** `strokeDasharray` of `[circumference *
  fraction, circumference]` gives one visible run and one gap. It is the standard
  trick and the reason no path maths appears here.
- **A shared visual does not mean shared meaning.** The ring and the tiles both
  show progress toward a number. They disagree about what passing it means, which
  is enough to keep them apart.
- **A green suite can be silent.** Every Today test used a null target set, so the
  whole feature could have shipped untested behind a passing run.

## Blast radius

One screen and two new components. No API change, no client regeneration, no
migration.

`react-native-svg` is native, so a development build must be rebuilt before the
ring appears on a device. Metro alone cannot deliver it.

## Deliberately unhandled

- **Animation.** The ring draws at its final value. `strokeDasharray` is the only
  surface MAC-61 needs if it wants motion.
- **Dynamic Type on the ring's big number.** It stays at a fixed size, because the
  ring cannot grow with it and a clipped number is worse than a fixed one. Every
  label around it scales.
- **The empty and first-run states** in screens 16 to 18. MAC-60 and MAC-61 own
  those.
- **Day navigation.** Already shipped with MAC-59's day picker.

## Open questions

None. The null-target behaviour was agreed before implementation.
