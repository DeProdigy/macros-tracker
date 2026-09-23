# MAC-77: Dismiss the keyboard after typing

Status: approved by Alex on 23 Sep 2026.

Linear: https://linear.app/hintology/issue/MAC-77/dismiss-keyboard-after-typing

## The bug

Alex saw this in onboarding. There are two causes, and both must be fixed.

1. **The keyboard covers the footer.** `Screen` in
   `apps/mobile/components/ui/screen.tsx` renders the footer as a sibling of the
   `KeyboardAvoidingView`, not as a child of it. The view lifts only the content
   above the footer. On the question screens, Back and Next stay under the
   keyboard.
2. **Nothing closes the keyboard.** Age, height, and weight use `number-pad` and
   `decimal-pad`. On iOS those keyboards have no Return key. The question page
   is a plain `View`, so a tap on empty space does nothing.

After you type your age, you cannot reach Next and you cannot close the
keyboard.

## Approach

Only built-in React Native parts. No new dependency and no new native build.

### `components/ui/screen.tsx`

- When `keyboard` is on, the footer moves inside the `KeyboardAvoidingView`. The
  footer then rides above the keyboard with the content.
- When `keyboard` is on and `scroll` is off, a `Pressable` wraps the body and
  calls `Keyboard.dismiss()`. It sets `accessible={false}` so VoiceOver does not
  announce the whole page as one button. The pattern is "tap outside to
  dismiss".
- The `ScrollView` gets `keyboardDismissMode="interactive"`. A drag down closes
  the keyboard, the same as in Messages. The existing
  `keyboardShouldPersistTaps="handled"` already closes it on a tap in empty
  space.

### New `components/ui/keyboard-done-bar.tsx`

A thin bar with a Done button that sits on top of the keyboard. It uses
`InputAccessoryView`, which is iOS only. On other platforms it renders nothing.
Inputs connect to it with `inputAccessoryViewID`.

One bar per screen, with one shared ID. `InputAccessoryView` matches by ID, so
several inputs can share one bar.

### Where the bar goes

Every number input, because every number keyboard has the same trap:

- `app/onboarding.tsx`: age, feet, inches, weight
- `app/(app)/log-food.tsx`: the decimal inputs
- `app/(app)/photo.tsx`: its text input
- `components/item-editor.tsx`: the quantity input

## Alternatives rejected

**`react-native-keyboard-controller`.** The ticket links it. It gives a sticky
footer, a Done toolbar, and up and down arrows between fields. It is a native
module, so it needs a new dev client and a new internal build. Its biggest gain
is on Android, where `KeyboardAvoidingView` is unreliable with edge-to-edge
layouts. START HERE puts Android out of MVP scope. The built-in parts fix the
iOS bug with a smaller change. Pick the library when Android enters scope, or
when a screen needs arrows between many fields.

**`returnKeyType` and `onSubmitEditing`.** These do nothing on a number pad,
because the number pad has no Return key.

**`TouchableWithoutFeedback` around the page.** It works, but React Native
recommends `Pressable` for new code.

## Concepts in play

- `KeyboardAvoidingView` pads only its own children. Anything outside it keeps
  its place, and the keyboard covers it.
- `InputAccessoryView` is the iOS name for the bar above a keyboard. Native iOS
  apps use it for Done on number pads.
- `keyboardShouldPersistTaps` decides what a tap does while the keyboard is
  open. `keyboardDismissMode` decides what a drag does.

## Blast radius

Every screen that renders `<Screen keyboard>`: onboarding, log food, and photo.
`targets.tsx` has no text input and does not change. No API change and no
generated client change.

## Deliberately unhandled

- With the keyboard open, the footer keeps its home-indicator padding. The gap
  above the keyboard is about 34 points larger than needed.
- No up and down arrows between the feet and inches fields.
- Android and web.

## Tests

- A tap on the body of a keyboard `Screen` calls `Keyboard.dismiss`.
- With `keyboard` on, the footer renders inside the keyboard-avoiding view.
- The onboarding number inputs carry the Done bar ID.

## Screenshots

Before and after of an onboarding question with the keyboard open, from the iOS
simulator.
