/**
 * Welcome (9a) and Verifying (9c) from doc 26.
 *
 * One file for two screens on purpose. 9b is Apple's own sheet, so the whole
 * flow is a single component with a state machine rather than a route each: a
 * push mid-sign-in would put an animation between the tap and the sheet, and a
 * back gesture in the middle of a token exchange has no sensible meaning.
 *
 * Routing after success belongs to MAC-31. This screen ends with tokens in the
 * Keychain and nothing else.
 */

import { useCreateSession } from "@macros/api-client";
import * as AppleAuthentication from "expo-apple-authentication";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View, useColorScheme } from "react-native";

import { AppleSignInCancelled, signInWithApple } from "@/lib/apple-sign-in";
import { saveTokens } from "@/lib/auth-storage";

/**
 * Where the flow is.
 *
 * `verifying` and `storing` are separate because they are separately visible:
 * each drives one of 9c's three lines. Collapsing them would leave the third
 * line permanently pending, which is worse than not drawing it.
 */
type Phase = "idle" | "authorizing" | "verifying" | "storing" | "done" | "error";

/** A 9c line is one of three states, and only one line is ever active. */
type StepState = "pending" | "active" | "done";

const VERIFYING_PHASES: Phase[] = ["authorizing", "verifying", "storing", "done"];

/**
 * Doc 26: three named lines, not an indeterminate spinner. Named because a
 * frozen view during a slow call reads as a crash, and a spinner says only
 * "something". These three are the real stages — each advances off actual
 * progress, never a timer, so the screen cannot claim to be further along than
 * it is.
 */
const stepStates = (phase: Phase): [StepState, StepState, StepState] => {
  const order = VERIFYING_PHASES.indexOf(phase);

  const stateFor = (index: number): StepState => {
    if (order > index) return "done";
    if (order === index) return "active";
    return "pending";
  };

  return [stateFor(0), stateFor(1), stateFor(2)];
};

export default function LoginScreen() {
  const scheme = useColorScheme();
  const isDark = scheme === "dark";

  const [phase, setPhase] = useState<Phase>("idle");
  const [isAppleAvailable, setIsAppleAvailable] = useState<boolean | null>(null);

  // Sign in with Apple exists only on iOS 13+. Checking rather than assuming
  // keeps the Android and simulator cases from throwing an unhandled native
  // error at tap time, which is the dead end the ticket rules out.
  useEffect(() => {
    let cancelled = false;

    AppleAuthentication.isAvailableAsync()
      .then((available) => {
        if (!cancelled) setIsAppleAvailable(available);
      })
      .catch(() => {
        if (!cancelled) setIsAppleAvailable(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const { mutateAsync: createSession } = useCreateSession();

  const handleSignIn = async () => {
    setPhase("authorizing");

    try {
      // Apple's sheet is modal and native: nothing of ours is on screen until
      // it resolves, which is why 9c starts here rather than before the call.
      const credential = await signInWithApple();

      setPhase("verifying");
      const response = await createSession({
        data: {
          identity_token: credential.identityToken,
          nonce: credential.nonce,
          ...(credential.name ? { name: credential.name } : {}),
        },
      });

      if (response.status !== 201) {
        setPhase("error");
        return;
      }

      setPhase("storing");
      await saveTokens({ access: response.data.access, refresh: response.data.refresh });
      setPhase("done");
    } catch (error) {
      // Dismissing Apple's sheet is a decision, not a failure. Showing an error
      // for it would blame the user for the thing they just chose.
      if (error instanceof AppleSignInCancelled) {
        setPhase("idle");
        return;
      }
      setPhase("error");
    }
  };

  const palette = isDark ? darkPalette : lightPalette;

  if (VERIFYING_PHASES.includes(phase)) {
    const [first, second, third] = stepStates(phase);

    return (
      <View style={[styles.container, { backgroundColor: palette.background }]}>
        <Text style={[styles.verifyingTitle, { color: palette.text }]}>Verifying</Text>
        <View style={styles.steps}>
          <Step label="Confirming it's you with Apple" state={first} palette={palette} />
          <Step label="Checking your Apple token" state={second} palette={palette} />
          <Step label="Saving your session to the Keychain" state={third} palette={palette} />
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: palette.background }]}>
      <View style={styles.hero}>
        <Text style={[styles.wordmark, { color: palette.text }]}>Macros</Text>
        <Text style={[styles.tagline, { color: palette.secondaryText }]}>
          Photograph a meal. Get the numbers.
        </Text>
      </View>

      <View style={styles.actions}>
        {phase === "error" ? (
          <View style={styles.errorBlock}>
            <Text style={[styles.errorText, { color: palette.error }]}>
              That sign-in didn&apos;t go through. Nothing was created, so try again.
            </Text>
          </View>
        ) : null}

        {isAppleAvailable === false ? (
          <Text style={[styles.errorText, { color: palette.error }]}>
            Sign in with Apple isn&apos;t available on this device. It needs iOS 13 or later.
          </Text>
        ) : (
          // Apple's own button component, not a lookalike. The Human Interface
          // Guidelines require the system button for Sign in with Apple, and a
          // hand-rolled one is a review rejection later for no gain now.
          <AppleAuthentication.AppleAuthenticationButton
            buttonStyle={
              isDark
                ? AppleAuthentication.AppleAuthenticationButtonStyle.WHITE
                : AppleAuthentication.AppleAuthenticationButtonStyle.BLACK
            }
            buttonType={AppleAuthentication.AppleAuthenticationButtonType.CONTINUE}
            cornerRadius={12}
            onPress={handleSignIn}
            style={styles.appleButton}
          />
        )}

        {/* Doc 26: this line does the work the deleted Register / Log in toggle
            used to. Without it a returning user hesitates over whether the tap
            is about to make them a second account. */}
        <Text style={[styles.sameAction, { color: palette.secondaryText }]}>
          New here or coming back, it&apos;s the same button.
        </Text>
      </View>

      {/* The dimmest text on the screen, and deliberately before the tap rather
          than buried in Settings — doc 26 calls it the only surprising thing
          about the data flow. */}
      <Text style={[styles.disclosure, { color: palette.dimText }]}>
        Meal photos are sent to an AI provider to be analysed.
      </Text>
    </View>
  );
}

type Palette = typeof lightPalette;

/** One line of 9c. The marker carries the state; the text never changes. */
const Step = ({ label, state, palette }: { label: string; state: StepState; palette: Palette }) => (
  <View style={styles.step}>
    <Text
      accessibilityElementsHidden
      style={[styles.stepMarker, { color: state === "pending" ? palette.dimText : palette.accent }]}
    >
      {state === "done" ? "✓" : "•"}
    </Text>
    <Text
      // The state is in the marker, which is decorative, so it has to be in the
      // label too or a screen reader hears three identical lines.
      accessibilityLabel={`${label}, ${state}`}
      style={[
        styles.stepLabel,
        { color: state === "pending" ? palette.dimText : palette.text },
        state === "active" && styles.stepLabelActive,
      ]}
    >
      {label}
    </Text>
  </View>
);

const lightPalette = {
  background: "#ffffff",
  text: "#111111",
  secondaryText: "#5a5a5a",
  dimText: "#9b9b9b",
  accent: "#208aef",
  error: "#c0392b",
};

const darkPalette: Palette = {
  background: "#000000",
  text: "#f5f5f5",
  secondaryText: "#a8a8a8",
  dimText: "#6b6b6b",
  accent: "#4ea3f5",
  error: "#ff6b5b",
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "space-between",
    paddingHorizontal: 32,
    paddingBottom: 48,
    paddingTop: 120,
  },
  hero: { gap: 12 },
  wordmark: { fontSize: 40, fontWeight: "700", letterSpacing: -1 },
  tagline: { fontSize: 17, lineHeight: 24 },
  actions: { gap: 16 },
  appleButton: { height: 52, width: "100%" },
  sameAction: { fontSize: 14, lineHeight: 20, textAlign: "center" },
  errorBlock: { gap: 8 },
  errorText: { fontSize: 14, lineHeight: 20, textAlign: "center" },
  disclosure: { fontSize: 12, lineHeight: 17, textAlign: "center" },
  verifyingTitle: { fontSize: 28, fontWeight: "600", marginBottom: 32 },
  steps: { gap: 16, marginBottom: "auto" },
  step: { alignItems: "flex-start", flexDirection: "row", gap: 12 },
  stepMarker: { fontSize: 16, lineHeight: 22, width: 18 },
  stepLabel: { flex: 1, fontSize: 16, lineHeight: 22 },
  stepLabelActive: { fontWeight: "600" },
});
