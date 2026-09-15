# MAC-70: Fix iOS launch crash from mismatched Expo native modules

Linear:
[MAC-70](https://linear.app/hintology/issue/MAC-70/fix-ios-launch-crash-from-mismatched-expo-native-modules).

## Problem

Every iOS build since MAC-54 closes at launch. The preview build `9e084ae4` and the development
build `848a0f50` both crash. The development build does not request a JS bundle from Metro, so the
crash happens before any app code runs.

## Evidence

Five crash reports from the iPhone (iOS 27.0, `iPhone18,1`) give the same reason. The reports came
over USB from `idevicecrashreport`.

```
namespace: DYLD, indicator: Symbol missing
Symbol not found: _$s15ExpoModulesCore10BaseModuleC11willDestroyyyFTj
Referenced from: MacrosTracker.app/Frameworks/ExpoImageManipulator.framework
Expected in:     MacrosTracker.app/Frameworks/ExpoModulesCore.framework
```

`dyld` is the iOS loader. It links every framework before `main()` runs. If one framework calls a
function that another framework does not export, `dyld` stops the app.

## Root cause

- MAC-54 (#48) added `expo-image-manipulator` and `expo-image-picker` with `^57.0.14`. Every other
  Expo package uses `~`, at the old SDK patch that `expo@57.0.8` shipped with.
- `expo@57.0.8` installs `expo-modules-core@57.0.7`.
- `expo-image-manipulator@57.0.14` calls `BaseModule.willDestroy()`.
- `expo-modules-core@57.0.7` does not have `willDestroy()`. `expo-modules-core@57.0.18` has it in
  `ios/Core/Modules/Module.swift`. Both tarballs were checked.
- `expo-image-manipulator` declares only `expo: *` as a peer. Nothing in pnpm stops the mismatch.
- Jest never loads native frameworks, so `pnpm pre-pr` and CI passed.

## Files touched

- `apps/mobile/package.json`
- `pnpm-lock.yaml`
- `plans/tickets/MAC-70.md`

## Approach

From `apps/mobile`, run `pnpm exec expo install --fix`. This command sets every Expo-managed
package to the version that SDK 57 expects today. `expo install --check` lists 23 packages. The
important ones:

- `expo` 57.0.8 to ~57.0.23, which brings `expo-modules-core` ~57.0.18
- `expo-image-manipulator` and `expo-image-picker` to ~57.0.18, with `~` in place of `^`
- `react-native` 0.86.0 to 0.86.3
- `react-native-reanimated` 4.5.0 to 4.5.1, and `react-native-worklets` 0.10.0 to 0.10.1
- `jest-expo` to ~57.0.5

Then:

1. Confirm that `pnpm exec expo install --check` exits 0.
2. Confirm that the installed `expo-modules-core` has `willDestroy()`.
3. Run `pnpm pre-pr`.
4. Start an EAS development build. Install it on the iPhone. Open the app.
5. Pull crash reports with `idevicecrashreport`. The check passes when the app shows its first
   screen and no new `MacrosTracker-*.ips` file appears.
6. Start an EAS preview build and repeat step 5.

## Alternatives rejected

- **Pin the two image packages down** to a version built against `expo-modules-core@57.0.7`. This
  needs a bisect to find that version. It also keeps `react-native` 0.86.0, which has the Hermes V1
  memory regression that `expo-doctor` reports.
- **Force `expo-modules-core` up with a pnpm override.** The core must match the `expo` package that
  depends on it. An override hides the mismatch. It does not remove it.
- **Remove the photo feature.** It deletes shipped MAC-54 work to avoid a version bump.

## Concepts in play

**Dynamic linking.** An iOS app is many frameworks. The loader resolves every cross-framework call
at launch. A missing symbol kills the app before any log, JS, or error screen can show. That is why
the development build closed with no red screen.

**Swift name mangling.** `_$s15ExpoModulesCore10BaseModuleC11willDestroyyyFTj` decodes to "the
dispatch thunk for `ExpoModulesCore.BaseModule.willDestroy()`". The numbers are name lengths. Read
the mangled name, and it tells you the exact module and method.

**`~` versus `^`.** `~57.0.14` accepts only 57.0.x patches. `^57.0.14` accepts any 57.x.y. Here
both ranges allow the bug, because the break is between two patches. The real rule is that Expo
packages move together.

**`expo install` versus `pnpm add`.** `expo install` picks versions that match the installed SDK.
`pnpm add` picks the newest version on npm. Use `expo install` for any package that has native
code.

**Why tests missed it.** Jest runs JS in Node, and it mocks native modules. It cannot see a native
link error. Only a native build that launches can.

## Horizontal ticket

This is a bug fix, not a slice. A user can now open the app on an iPhone.

## Blast radius

Wide at the native layer, small in app code. React Native, Hermes, and every Expo native module get
a patch bump. Every existing iOS install keeps crashing until a new EAS build replaces it. No API
change, so no `generate:api` diff. No UI change.

## Deliberately unhandled

- **No automated regression test.** No correct seam exists in this repo. Jest cannot load native
  frameworks. The only test that catches this failure is a native build that launches on a device
  or simulator. That belongs in a separate ticket, for example an EAS build with a Maestro launch
  check.
- **iOS 27.** The phone runs iOS 27.0. The crash report shows a link error, not an iOS 27 problem.
  This ticket does not test iOS 26.
- **Android.** iOS only, same as MAC-20.

## Open questions

1. **Add `expo install --check` to `pnpm pre-pr` or CI?** Decision: no, as recommended. The check
   reads the newest SDK patch from Expo's servers. It fails every time Expo ships a patch, even with
   no repo change. Its offline mode would not have caught this bug, because `~` allows the newer
   patch. A device launch check is the right guard, in a separate ticket.
2. **Screenshots.** The PR changes no UI. It states that screenshots are not applicable and
   describes the device launch check.
