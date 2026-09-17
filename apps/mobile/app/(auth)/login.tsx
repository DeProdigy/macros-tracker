/**
 * Welcome (9a) and Verifying (9c) from doc 26.
 *
 * One file for two screens on purpose. 9b is Apple's own sheet, so the whole
 * flow is a single component with a state machine rather than a route each: a
 * push mid-sign-in would put an animation between the tap and the sheet, and a
 * back gesture in the middle of a token exchange has no sensible meaning.
 *
 * MAC-31 added the ending: tokens land in the Keychain, the session adopts the
 * user the API returned, and the screen redirects. Where to is the same
 * question the launch gate asks, answered from the same field.
 *
 * MAC-61 took the presentation from design/source/linear-2026-08-31/
 * 01-auth-welcome.png. That artifact defines the look of this screen only. The
 * copy is unchanged, because a screenshot cannot rewrite settled wording.
 */

import { ApiError, useCreateSession } from "@macros/api-client";
import * as AppleAuthentication from "expo-apple-authentication";
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import { Screen } from "@/components/ui/screen";
import { Body, Caption, ErrorText, Lead, Title } from "@/components/ui/text";
import { AppleSignInCancelled, signInWithApple } from "@/lib/apple-sign-in";
import { saveTokens } from "@/lib/auth-storage";
import { needsOnboarding } from "@/lib/onboarding";
import { useSession } from "@/lib/session";
import { colors, radius, space } from "@/lib/theme";

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

/**
 * Which failure to explain.
 *
 * The distinction is about what the user can do next, not about the status
 * code. A rejected credential is worth retrying; a 5xx means the server is
 * broken and retrying now fails identically. Telling someone to try again when
 * it cannot work is the same lie a spinner tells.
 *
 * Everything below 500 collapses into one message on purpose. The API answers
 * every verification failure with the same opaque 401 so the endpoint is not an
 * oracle, so there is nothing more specific to say even if we wanted to.
 */
type ErrorKind = "credential" | "server";

const errorKindOf = (error: unknown): ErrorKind =>
  error instanceof ApiError && error.status >= 500 ? "server" : "credential";

const ERROR_COPY: Record<ErrorKind, string> = {
  credential: "That sign-in didn't go through. Nothing was created, so try again.",
  server:
    "Something went wrong on our end. Nothing was created, and it isn't your doing. Try again in a minute.",
};

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
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorKind, setErrorKind] = useState<ErrorKind>("credential");
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
  const session = useSession();

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
        // Unreachable in practice: customFetch throws on every non-2xx, so this
        // catches only a 2xx that is not 201 — a proxy rewriting the status, say.
        setErrorKind("credential");
        setPhase("error");
        return;
      }

      setPhase("storing");
      // Tokens first, then state. The redirect below lands on a screen that
      // immediately makes an authenticated request, and a Keychain write that
      // has not finished is a 401 on the first frame of Today.
      await saveTokens({ access: response.data.access, refresh: response.data.refresh });
      session.signIn(response.data.user);
      setPhase("done");
    } catch (error) {
      // Dismissing Apple's sheet is a decision, not a failure. Showing an error
      // for it would blame the user for the thing they just chose.
      if (error instanceof AppleSignInCancelled) {
        setPhase("idle");
        return;
      }
      setErrorKind(errorKindOf(error));
      setPhase("error");
    }
  };

  // `created` is not consulted. A returning user whose onboarding never
  // finished belongs in the same place as a brand-new one, and the server
  // tracks that on the user rather than in anything this screen knows.
  //
  // Same helper as the launch gate. Sign-in and cold start have to agree, and
  // the only way to guarantee that is to run the same function.
  if (phase === "done" && session.status === "signedIn") {
    return needsOnboarding(session.user) ? (
      <Redirect href="/onboarding" />
    ) : (
      <Redirect href="/today" />
    );
  }

  if (VERIFYING_PHASES.includes(phase)) {
    const [first, second, third] = stepStates(phase);

    return (
      <Screen contentStyle={styles.verifyingPage}>
        <Title style={styles.verifyingTitle}>Verifying</Title>
        <View style={styles.steps}>
          <Step label="Confirming it's you with Apple" state={first} />
          <Step label="Checking your Apple token" state={second} />
          <Step label="Saving your session to the Keychain" state={third} />
        </View>
      </Screen>
    );
  }

  return (
    <Screen contentStyle={styles.page}>
      <View style={styles.hero}>
        <View style={styles.wordmark}>
          <Title>Macros</Title>
          {/* The one piece of decoration in the app, and it comes from the
              approved Welcome screen. It is hidden from VoiceOver because it
              says nothing a reader needs. */}
          <View accessibilityElementsHidden importantForAccessibility="no" style={styles.dot} />
        </View>
        <Lead>Photograph a meal. Get the numbers.</Lead>
      </View>

      <View style={styles.actions}>
        {phase === "error" ? (
          <ErrorText style={styles.centred}>{ERROR_COPY[errorKind]}</ErrorText>
        ) : null}

        {isAppleAvailable === false ? (
          <ErrorText style={styles.centred}>
            Sign in with Apple isn&apos;t available on this device. It needs iOS 13 or later.
          </ErrorText>
        ) : (
          // Apple's own button component, not a lookalike. The Human Interface
          // Guidelines require the system button for Sign in with Apple, and a
          // hand-rolled one is a review rejection later for no gain now.
          //
          // It does not use our `Button`, and it never should. Apple owns this
          // control's size, wording, and look.
          <AppleAuthentication.AppleAuthenticationButton
            // Always the white button. The app is dark only as of MAC-61, so
            // the black variant would be a black button on a black screen.
            buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
            buttonType={AppleAuthentication.AppleAuthenticationButtonType.CONTINUE}
            cornerRadius={radius.md}
            onPress={handleSignIn}
            style={styles.appleButton}
          />
        )}

        {/* Doc 26: this line does the work the deleted Register / Log in toggle
            used to. Without it a returning user hesitates over whether the tap
            is about to make them a second account. */}
        <Body color={colors.textSecondary} style={styles.centred}>
          New here or coming back, it&apos;s the same button.
        </Body>
      </View>

      {/* The dimmest text on the screen, and deliberately before the tap rather
          than buried in Settings — doc 26 calls it the only surprising thing
          about the data flow. */}
      <Caption color={colors.textDim} style={styles.centred}>
        Meal photos are sent to an AI provider to be analysed.
      </Caption>
    </Screen>
  );
}

/** One line of 9c. The marker carries the state; the text never changes. */
const Step = ({ label, state }: { label: string; state: StepState }) => (
  <View style={styles.step}>
    <Body
      accessibilityElementsHidden
      color={state === "pending" ? colors.textDim : colors.accent}
      style={styles.stepMarker}
    >
      {state === "done" ? "✓" : "•"}
    </Body>
    <Body
      // The state is in the marker, which is decorative, so it has to be in the
      // label too or a screen reader hears three identical lines.
      accessibilityLabel={`${label}, ${state}`}
      color={state === "pending" ? colors.textDim : colors.text}
      style={styles.stepLabel}
    >
      {label}
    </Body>
  </View>
);

const styles = StyleSheet.create({
  actions: { gap: space.lg },
  appleButton: { height: 52, width: "100%" },
  centred: { textAlign: "center" },
  dot: { backgroundColor: colors.accent, borderRadius: radius.full, height: 10, width: 10 },
  hero: { gap: space.md },
  page: {
    justifyContent: "space-between",
    paddingBottom: space.section,
    paddingHorizontal: space.xxl,
    // The hero sits low rather than under the notch, as the approved screen
    // draws it. `paddingTop` on the content, not the page, so the safe-area
    // inset still applies above it.
    paddingTop: 120,
  },
  step: { alignItems: "flex-start", flexDirection: "row", gap: space.md },
  stepLabel: { flex: 1, lineHeight: 22 },
  stepMarker: { lineHeight: 22, width: 18 },
  steps: { gap: space.lg, marginBottom: "auto" },
  verifyingPage: { paddingHorizontal: space.xxl, paddingTop: space.section },
  verifyingTitle: { marginBottom: space.xxl },
  wordmark: { alignItems: "flex-end", flexDirection: "row", gap: space.sm },
});
