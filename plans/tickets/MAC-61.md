# MAC-61: MVP visual and accessibility polish across the daily loop

Status: approved by Alex on 17 Sep 2026.

Linear: https://linear.app/hintology/issue/MAC-61/mvp-visual-and-accessibility-polish-across-the-daily-loop

## What this ticket is

The daily loop works. It does not look like one app. This ticket makes the 18
mobile screens share one token system, fit real iPhone hardware, and survive
VoiceOver and large text.

This is a horizontal ticket. The allowed reason is the third one in CLAUDE.md:
the plan gate makes tickets expensive. A token system cut into slices means the
same 18 files get touched five times. It is also the fourth reason: this is the
last ticket in MVP 3, and MVP 4 is a TestFlight release. The polish must land
before the build that Alex installs.

There is no new user capability here. The ticket's own sentence is the honest
one: a user can now complete the daily loop through one coherent and accessible
interface.

## What the code looks like today

I measured the mobile app before planning.

| Fact | Count |
| -- | -- |
| Screens and components with their own `StyleSheet` | 18 |
| Distinct `fontSize` values | 22 |
| Distinct padding, margin, and gap values | 30 |
| Distinct `borderRadius` values | 7 |
| Hex colours written outside `lib/palette.ts` | 32 |
| Files that read safe-area insets | 0 |
| Screens with text inputs and no `KeyboardAvoidingView` | 4 |
| Calls to `allowFontScaling` or `maxFontSizeMultiplier` | 0 |

`app/(app)/today.tsx` shows the pattern. It hardcodes `paddingTop: 68` and
`bottom: 34` for the notch and the home indicator. Those two numbers are right
on one device and wrong on the rest.

The good news is smaller than it sounds. No screen contains a streak chip, a
meal group, an Advice row, or a Recap. Those elements only exist in the
mockups. That acceptance criterion is already met, and the work is to keep it
met while copying presentation from artwork that still shows them.

## The colour tokens, and where they come from

I read the pixels out of the approved-direction mockups rather than picking
values. These are the dominant colours across `19-today-normal.png`,
`20-today-over-target.png`, `01-auth-welcome.png`, `12-log-review.png`,
`05-onboarding-question.png`, and `37-settings.png`.

| Token | Hex | Job |
| -- | -- | -- |
| `background` | `#000000` | The page. True black, as the canonical direction asks |
| `surface` | `#0e1013` | Cards, tiles, and rows |
| `surfaceRaised` | `#1b1e23` | A card on a card, and input fills |
| `border` | `#242628` | Hairlines and input outlines |
| `accent` | `#5ee7e0` | Cyan primary. Calories, links, and the primary button |
| `accentDim` | `#265151` | The calorie ring track and tinted accent fills |
| `text` | `#ffffff` | Primary text and numerals |
| `textSecondary` | `#8b8f98` | Labels, units, and support text |
| `textDim` | `#4a4e55` | Disabled text and decoration only. See the contrast note |
| `warning` | `#ffa24d` | Calories over target |
| `positive` | `#7beba4` | A gram target reached |
| `protein` | `#b79cff` | Protein under target |
| `warningSurface` | `#1a1108` | The tinted panel behind an over-target day |

Two of these change what the app shows today. The accent moves from blue
`#4ea3f5` to cyan `#5ee7e0`. The met-target green moves from `#4ade80` to
`#7beba4`. Both changes follow the artwork.

### The contrast finding

I computed WCAG contrast ratios against `#000000` and against `#0e1013`.

| Colour | On black | On surface | AA body text (4.5:1) |
| -- | -- | -- | -- |
| `#ffffff` | 21.00 | 19.05 | Pass |
| `#5ee7e0` | 13.98 | 12.69 | Pass |
| `#7beba4` | 14.26 | 12.94 | Pass |
| `#ffa24d` | 10.53 | 9.55 | Pass |
| `#b79cff` | 9.21 | 8.36 | Pass |
| `#8b8f98` | 6.48 | 5.88 | Pass |
| `#4a4e55` | 2.51 | 2.28 | **Fail** |

The mockups use `#4a4e55` for entry timestamps. A timestamp carries meaning, so
that colour fails where the artwork puts it.

Alex decided on 17 Sep 2026 that the artwork wins. `#4a4e55` stays on entry
timestamps exactly as drawn. The app has one user, and that user chose the look.

Two things follow from the decision, and the PR description states both.

1. Entry timestamps do not meet WCAG AA. Every other text pair in the token
   table does. This is a known and accepted gap, not an oversight.
2. The contrast unit test asserts the ratios for the other pairs only. It
   carries a comment naming the exemption, so a later reader does not think the
   test is wrong.

`#4a4e55` stays out of every other text role. Disabled controls, decoration,
and entry timestamps are its whole job.

Black text on the cyan button reaches 13.98:1, so the existing primary button
keeps its dark label.

## Decisions Alex already made

All five were answered on 17 Sep 2026.

1. **Dark only.** All 46 mockups are dark. No light artwork exists, so the
   current light palette is invention. `userInterfaceStyle` becomes `dark`.
2. **Two pull requests.** PR 1 builds the system. PR 2 applies it.
3. **The artwork wins on timestamp contrast.** See the contrast section.
4. **Generate a simple app icon.** A black tile with a cyan mark. It replaces
   the Expo default so the TestFlight build does not carry it. The icon is my
   drawing, not approved design work, and the PR says so.
5. **Simulator screenshots for the PR.** Alex does the physical-device
   walkthrough as the acceptance step.

## PR 1: the system

Nothing in PR 1 changes a screen's layout. It adds the tokens, the fonts, the
primitives, and the safe-area base, and it makes the app dark only.

### Files

| File | Change |
| -- | -- |
| `apps/mobile/lib/theme.ts` | New. Colour, spacing, radius, and type tokens |
| `apps/mobile/lib/palette.ts` | Deleted. `theme.ts` replaces it |
| `apps/mobile/components/ui/text.tsx` | New. `Display`, `Title`, `Heading`, `Body`, `Label`, `Mono`, `Numeral` |
| `apps/mobile/components/ui/screen.tsx` | New. Safe-area page wrapper with optional keyboard avoidance |
| `apps/mobile/components/ui/button.tsx` | New. Primary, secondary, and destructive. 44-point floor |
| `apps/mobile/app/_layout.tsx` | Add `SafeAreaProvider`. Load fonts. Hold the splash until fonts resolve. `StatusBar` becomes `light` |
| `apps/mobile/app.json` | `userInterfaceStyle: "dark"`. Splash background to `#000000`. Drop dead asset references |
| `apps/mobile/package.json` | Add `@expo-google-fonts/archivo` and `@expo-google-fonts/ibm-plex-mono` |
| `apps/mobile/assets/images/` | Delete `react-logo*.png`, `expo-badge*.png`, `expo-logo.png`, `logo-glow.png`, `tutorial-web.png` |
| `apps/mobile/__tests__/theme.test.ts` | New. Contrast assertions on the token pairs |
| `apps/mobile/__tests__/ui-primitives.test.tsx` | New. Button floor height, screen insets, text scaling caps |

### The compatibility shim

18 files call `usePalette()`. PR 1 keeps that export in `theme.ts`, returning
the dark tokens. Screens compile unchanged. PR 2 deletes the hook as it
rewrites each screen.

The hook exists in PR 1 only to keep the diff readable. A hook implies the
value can change between renders. Under dark only it cannot, so it is a lie
with an expiry date, and the code comment will say so.

### The type scale

Seven sizes replace 22. Archivo carries UI text and numerals. IBM Plex Mono
carries labels, units, dates, times, and metric strings, which is what the
canonical direction asks for.

| Name | Size | Family | Used for |
| -- | -- | -- | -- |
| `display` | 52 | Archivo 800 | The calorie number in the ring |
| `title` | 34 | Archivo 800 | Screen titles |
| `heading` | 22 | Archivo 700 | Section and card titles |
| `numeral` | 30 | Archivo 700 | Tile values |
| `body` | 16 | Archivo 400 | Sentences |
| `label` | 12 | Plex Mono 500, tracked | Uppercase labels and units |
| `caption` | 13 | Plex Mono 400 | Times and metric strings |

### The spacing scale

Six steps replace 30 values: 4, 8, 12, 16, 24, and 32. A 48 and a 64 stay for
page rhythm. Radii collapse to 8, 12, and 16.

### Fonts and the splash

`expo-font` loads the two families in the root layout. The splash stays up
until they resolve. Without the gate the app paints in the system font and then
swaps, which reads as a flicker on every cold start. This is the standard
flash-of-unstyled-text problem, and holding the splash is the standard answer.

The cost is bundle size and a slightly longer cold start. Both are acceptable
for a personal TestFlight build.

## PR 2: the screens

Each screen loses its ad-hoc styles and takes the primitives.

### Files

All 18, in this order. The order follows the daily loop, so a partial review
still reads as a journey.

1. `app/(auth)/login.tsx`
2. `app/onboarding.tsx`
3. `app/targets.tsx`
4. `app/first-food.tsx`
5. `app/(app)/today.tsx`
6. `components/calorie-ring.tsx`
7. `components/macro-tile.tsx`
8. `components/day-picker.tsx`
9. `app/(app)/log-food.tsx`
10. `app/(app)/photo.tsx`
11. `components/item-editor.tsx`
12. `app/(app)/entry/[id].tsx`
13. `app/(app)/settings.tsx`
14. `app/(app)/target-history.tsx`
15. `app/(app)/health.tsx`
16. `app/index.tsx`
17. `app/(app)/_layout.tsx`
18. `app/_layout.tsx`

### The accessibility pass

- **Safe areas.** Every screen adopts the `Screen` wrapper. The hardcoded 68
  and 34 in `today.tsx` are deleted.
- **Keyboard.** `onboarding.tsx`, `log-food.tsx`, `photo.tsx`, and
  `item-editor.tsx` gain keyboard avoidance. iOS uses `padding`. Android uses
  `height`. The two platforms report the keyboard differently, so one value
  does not serve both.
- **Dynamic Type.** Body text scales without a cap. Numerals inside the ring
  and the tiles take `maxFontSizeMultiplier` of about 1.4, because a 52-point
  number at 310 percent leaves the ring. Every row that holds a number beside
  text gets checked at the largest accessibility size.
- **Tap targets.** Every interactive element reaches 44 points. Current
  minimums are 48 or above where they are set at all, so this is mostly about
  the elements that set nothing.
- **VoiceOver.** Every `Pressable` gets a role and a label. `settings.tsx` has
  six pressables and five roles today, so at least one is unlabelled. Error
  text keeps `accessibilityRole="alert"`.
- **Contrast.** The token table above is the rule, with the entry-timestamp
  exemption Alex approved. A unit test asserts the ratios so a later colour
  edit cannot quietly break them.

### Tests

26 test files exist. Several render screens and assert on text. The token swap
should not break them, but the font-loading gate in the root layout can, since
a test render now waits for fonts. The plan mocks the font hook in
`test-utils/render.tsx` so screens render synchronously.

## Alternatives rejected

**A styling library.** NativeWind, Tamagui, or Unistyles each solve this.
Each also adds a build step, a dependency, and a second way to write a style.
React Native's own `StyleSheet` plus a token module solves the actual problem,
which is 22 font sizes, not a missing feature. This would be the wrong call on
a larger team, or with more than one theme, or with a web target that shares
components. None of those apply.

**One pull request.** Alex chose two. The diff across 18 screens is about 2500
lines, which nobody reviews properly in one sitting.

**Keeping light mode.** No approved light artwork exists. Inventing one doubles
the token set and the contrast work, and produces a look nobody signed off.

**Per-screen `useSafeAreaInsets`.** A wrapper component is the version that a
screen written next month cannot forget. The wrapper takes an `edges` prop for
the camera screen, which wants its preview to bleed under the notch.

**Copying the mockups pixel for pixel.** Files 19 and 20 are marked "Candidate
— revise" in the canonical review. They still show a streak chip and an Advice
row. The plan takes colour, type, and rhythm from them, and takes scope from
the canonical flow.

## React Native concepts in play

- **Design tokens.** One module owns the values. The alternative is what exists
  now, where a colour change means 32 edits and one gets missed.
- **`useColorScheme`.** The app currently branches on the OS theme. Dark only
  removes the branch. The lesson is that a theme hook is a cost, and it is only
  worth paying when two designs exist.
- **Safe-area insets.** `react-native-safe-area-context` reports the notch and
  the home indicator per device. A hardcoded padding is correct on exactly one
  phone.
- **Dynamic Type.** iOS scales text by a user setting. React Native honours it
  through `allowFontScaling`, which is on by default. Capping it is a last
  resort, and it belongs on numbers inside fixed geometry, never on prose.
- **`KeyboardAvoidingView`.** The `behavior` prop differs by platform because
  the platforms report keyboard frames differently.
- **Font loading.** Custom fonts arrive asynchronously. Rendering before they
  land shows the fallback font and then swaps.

## Blast radius

Every mobile screen changes. Nothing else does.

- No Django change.
- No API change, so no `pnpm generate:api` and no drift risk.
- 26 mobile test files may need updates where they assert on colour.
- The EAS build config is untouched, but the splash and icon change means MVP 4
  produces a visibly different build.

## Deliberately unhandled

- **Motion.** The ticket puts elaborate motion out of scope. No animation work.
- **A new brand direction.** The tokens come from the approved artwork.
- **Android polish.** The product targets Alex's iPhone. Android styles stay
  correct but unreviewed.
- **Design artifact approval.** I will not mark any PNG Approved in
  `design/README.md`. The canonical intake checklist gives that to Alex.
- **A designed app icon.** PR 1 ships a plain black tile with a cyan mark. It
  removes the Expo default. It is not a brand mark, and a later ticket can
  replace it.
- **The physical-device walkthrough.** Acceptance needs Alex on hardware.
- **The design-quality skill.** The ticket mentions an optional skill in
  preserve-system mode. No such skill is installed in this environment.

## Open questions

None remain. All five decisions are recorded above.

One thing to watch during PR 2. The canonical inventory asks for a Today state
called "protein or fiber cleared". The current `macro-tile.tsx` shows
`TARGET MET`, which covers it. If the artwork means something more than a
colour change, that is a behaviour question for Alex, and the plan stops rather
than inventing it.
