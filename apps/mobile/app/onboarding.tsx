/**
 * Mandatory first-run questions and deterministic target proposal (MAC-42).
 *
 * Answers live on this route while the user moves between questions. Nothing
 * is persisted here: MAC-43 turns an accepted proposal into a TargetVersion.
 */
import {
  ActivityEnum,
  ApiError,
  GoalEnum,
  TargetProposalRequestSexEnum,
  createTargetProposal,
  type TargetProposal,
  type TargetProposalRequestRequest,
} from "@macros/api-client";
import { Redirect } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { needsOnboarding } from "@/lib/onboarding";
import { usePalette, type Palette } from "@/lib/palette";
import { useSession } from "@/lib/session";

type Answers = {
  age: string;
  sex: TargetProposalRequestRequest["sex"] | null;
  heightFeet: string;
  heightInches: string;
  weight: string;
  goal: TargetProposalRequestRequest["goal"] | null;
  activity: TargetProposalRequestRequest["activity"] | null;
};

const EMPTY_ANSWERS: Answers = {
  age: "",
  sex: null,
  heightFeet: "",
  heightInches: "",
  weight: "",
  goal: null,
  activity: null,
};

const QUESTIONS = [
  ["How old are you?", "Age helps estimate how much energy your body uses."],
  ["What is your biological sex?", "The target formula uses this input."],
  ["How tall are you?", "Use feet and inches."],
  ["What do you weigh?", "Use your current weight in pounds."],
  ["What is your goal?", "This adjusts calories while keeping protein useful."],
  ["How active is your day?", "Count ordinary daily movement, outside deliberate workouts."],
] as const;

const LAST_QUESTION_INDEX = QUESTIONS.length - 1;

const numeric = (value: string): number | null => {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export const validateQuestion = (step: number, answers: Answers): string | null => {
  if (step === 0) {
    const age = numeric(answers.age);
    return age !== null && Number.isInteger(age) && age >= 13 && age <= 100
      ? null
      : "Enter an age from 13 to 100.";
  }
  if (step === 1) return answers.sex ? null : "Choose one option.";
  if (step === 2) {
    const feet = numeric(answers.heightFeet);
    const inches = numeric(answers.heightInches);
    const total = feet !== null && inches !== null ? feet * 12 + inches : null;
    return feet !== null &&
      Number.isInteger(feet) &&
      inches !== null &&
      Number.isInteger(inches) &&
      inches >= 0 &&
      inches <= 11 &&
      total !== null &&
      total >= 36 &&
      total <= 96
      ? null
      : "Enter a height from 3'0\" to 8'0\".";
  }
  if (step === 3) {
    const weight = numeric(answers.weight);
    return weight !== null && weight >= 85 && weight <= 500
      ? null
      : "Enter a weight from 85 to 500 lb.";
  }
  if (step === 4) return answers.goal ? null : "Choose one goal.";
  return answers.activity ? null : "Choose one activity level.";
};

const requestFrom = (answers: Answers): TargetProposalRequestRequest => ({
  age: Number(answers.age),
  sex: answers.sex as TargetProposalRequestRequest["sex"],
  height_in: Number(answers.heightFeet) * 12 + Number(answers.heightInches),
  weight_lb: Number(answers.weight).toFixed(2),
  goal: answers.goal as TargetProposalRequestRequest["goal"],
  activity: answers.activity as TargetProposalRequestRequest["activity"],
});

export default function Onboarding() {
  const session = useSession();
  const palette = usePalette();
  const [answers, setAnswers] = useState(EMPTY_ANSWERS);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [proposal, setProposal] = useState<TargetProposal | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  if (session.status === "loading") return null;
  if (session.status === "signedOut") return <Redirect href="/login" />;
  if (!needsOnboarding(session.user)) return <Redirect href="/today" />;

  const update = <K extends keyof Answers>(key: K, value: Answers[K]) => {
    setAnswers((current) => ({ ...current, [key]: value }));
    setError(null);
  };

  const next = async () => {
    const validation = validateQuestion(step, answers);
    if (validation) return setError(validation);
    if (step < LAST_QUESTION_INDEX) {
      setStep((current) => current + 1);
      setError(null);
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const response = await createTargetProposal(requestFrom(answers));
      if (response.status === 200) setProposal(response.data);
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 400
          ? "One of those answers was refused. Check your answers and try again."
          : "We couldn't calculate your targets. Your answers are still here. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (proposal) {
    return (
      <ScrollView
        contentContainerStyle={[styles.resultScreen, { backgroundColor: palette.background }]}
      >
        <Text style={[styles.eyebrow, { color: palette.accent }]}>YOUR DAILY TARGETS</Text>
        <Text style={[styles.title, { color: palette.text }]}>
          A starting point built from you.
        </Text>
        <View style={[styles.result, { borderColor: palette.hairline }]}>
          <Metric
            label="CALORIES"
            value={proposal.targets.calories}
            unit="KCAL"
            palette={palette}
          />
          <Metric label="PROTEIN" value={proposal.targets.protein_g} unit="G" palette={palette} />
          <Metric label="FIBER" value={proposal.targets.fiber_g} unit="G" palette={palette} />
        </View>
        {proposal.clamped ? (
          <Text
            style={[styles.notice, { borderColor: palette.hairline, color: palette.secondaryText }]}
          >
            The safe range adjusted the raw estimate before showing it.
          </Text>
        ) : null}
        <Text style={[styles.sectionLabel, { color: palette.dimText }]}>WHY THESE NUMBERS</Text>
        <Text style={[styles.body, { color: palette.secondaryText }]}>{proposal.rationale}</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            setProposal(null);
            setStep(LAST_QUESTION_INDEX);
          }}
          style={[styles.secondaryButton, { borderColor: palette.hairline }]}
        >
          <Text style={[styles.secondaryLabel, { color: palette.text }]}>BACK TO ANSWERS</Text>
        </Pressable>
        <Text style={[styles.body, { color: palette.dimText }]}>
          Accepting or adjusting these targets is the next build slice.
        </Text>
      </ScrollView>
    );
  }

  const [title, help] = QUESTIONS[step];
  return (
    <View style={[styles.screen, { backgroundColor: palette.background }]}>
      <View style={styles.progressRow}>
        {QUESTIONS.map((_, index) => (
          <View
            key={index}
            style={[
              styles.progress,
              { backgroundColor: index <= step ? palette.accent : palette.hairline },
            ]}
          />
        ))}
      </View>
      <ScrollView
        contentContainerStyle={styles.questionContent}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[styles.eyebrow, { color: palette.dimText }]}>
          {step + 1} OF {QUESTIONS.length}
        </Text>
        <Text style={[styles.title, { color: palette.text }]}>{title}</Text>
        <Text style={[styles.body, { color: palette.secondaryText }]}>{help}</Text>
        <QuestionControl step={step} answers={answers} update={update} palette={palette} />
        {error ? (
          <Text accessibilityRole="alert" style={[styles.error, { color: palette.error }]}>
            {error}
          </Text>
        ) : null}
      </ScrollView>
      <View style={styles.actions}>
        {step > 0 ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              setStep((current) => current - 1);
              setError(null);
            }}
            style={[styles.backButton, { borderColor: palette.hairline }]}
          >
            <Text style={[styles.secondaryLabel, { color: palette.text }]}>BACK</Text>
          </Pressable>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={signingOut}
            onPress={() => {
              setSigningOut(true);
              void session.signOut();
            }}
            style={styles.signOut}
          >
            <Text style={[styles.secondaryLabel, { color: palette.secondaryText }]}>
              {signingOut ? "SIGNING OUT…" : "SIGN OUT"}
            </Text>
          </Pressable>
        )}
        <Pressable
          accessibilityRole="button"
          disabled={submitting}
          onPress={() => void next()}
          style={[styles.nextButton, { backgroundColor: palette.accent }]}
        >
          {submitting ? (
            <ActivityIndicator color="#001111" />
          ) : (
            <Text style={styles.nextLabel}>
              {step === LAST_QUESTION_INDEX ? "BUILD MY TARGETS" : "NEXT"}
            </Text>
          )}
        </Pressable>
      </View>
    </View>
  );
}

function QuestionControl({
  step,
  answers,
  update,
  palette,
}: {
  step: number;
  answers: Answers;
  update: <K extends keyof Answers>(key: K, value: Answers[K]) => void;
  palette: Palette;
}) {
  const input = [styles.input, { borderColor: palette.hairline, color: palette.text }];
  if (step === 0)
    return (
      <TextInput
        accessibilityLabel="Age in years"
        autoFocus
        keyboardType="number-pad"
        maxLength={3}
        onChangeText={(value) => update("age", value)}
        placeholder="34"
        placeholderTextColor={palette.dimText}
        style={input}
        value={answers.age}
      />
    );
  if (step === 1)
    return (
      <ChoiceList
        items={[
          ["Female", TargetProposalRequestSexEnum.female],
          ["Male", TargetProposalRequestSexEnum.male],
        ]}
        selected={answers.sex}
        onSelect={(value) => update("sex", value)}
        palette={palette}
      />
    );
  if (step === 2)
    return (
      <View style={styles.inline}>
        <TextInput
          accessibilityLabel="Height feet"
          keyboardType="number-pad"
          maxLength={1}
          onChangeText={(value) => update("heightFeet", value)}
          placeholder="5 ft"
          placeholderTextColor={palette.dimText}
          style={[input, styles.half]}
          value={answers.heightFeet}
        />
        <TextInput
          accessibilityLabel="Height inches"
          keyboardType="number-pad"
          maxLength={2}
          onChangeText={(value) => update("heightInches", value)}
          placeholder="11 in"
          placeholderTextColor={palette.dimText}
          style={[input, styles.half]}
          value={answers.heightInches}
        />
      </View>
    );
  if (step === 3)
    return (
      <TextInput
        accessibilityLabel="Weight in pounds"
        keyboardType="decimal-pad"
        maxLength={6}
        onChangeText={(value) => update("weight", value)}
        placeholder="185 lb"
        placeholderTextColor={palette.dimText}
        style={input}
        value={answers.weight}
      />
    );
  if (step === 4)
    return (
      <ChoiceList
        items={[
          ["Lose weight", GoalEnum.cut],
          ["Maintain weight", GoalEnum.maintain],
          ["Gain weight", GoalEnum.gain],
        ]}
        selected={answers.goal}
        onSelect={(value) => update("goal", value)}
        palette={palette}
      />
    );
  return (
    <ChoiceList
      items={[
        ["Mostly seated", ActivityEnum.sedentary],
        ["Lightly active", ActivityEnum.light],
        ["Active most days", ActivityEnum.moderate],
        ["Very active", ActivityEnum.very_active],
      ]}
      selected={answers.activity}
      onSelect={(value) => update("activity", value)}
      palette={palette}
    />
  );
}

function ChoiceList<T extends string>({
  items,
  selected,
  onSelect,
  palette,
}: {
  items: readonly (readonly [string, T])[];
  selected: T | null;
  onSelect: (value: T) => void;
  palette: Palette;
}) {
  return (
    <View style={styles.choiceList}>
      {items.map(([label, value]) => {
        const chosen = selected === value;
        return (
          <Pressable
            accessibilityRole="radio"
            accessibilityState={{ checked: chosen }}
            key={value}
            onPress={() => onSelect(value)}
            style={[
              styles.choice,
              {
                backgroundColor: chosen ? palette.accent : palette.background,
                borderColor: chosen ? palette.accent : palette.hairline,
              },
            ]}
          >
            <Text style={[styles.choiceLabel, { color: chosen ? "#001111" : palette.text }]}>
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function Metric({
  label,
  value,
  unit,
  palette,
}: {
  label: string;
  value: number;
  unit: string;
  palette: Palette;
}) {
  return (
    <View accessibilityLabel={`${label} ${value} ${unit}`} style={styles.metric}>
      <Text style={[styles.sectionLabel, { color: palette.dimText }]}>{label}</Text>
      <Text style={[styles.metricValue, { color: palette.accent }]}>
        {value}
        <Text style={[styles.metricUnit, { color: palette.secondaryText }]}> {unit}</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, paddingBottom: 28, paddingHorizontal: 28, paddingTop: 64 },
  resultScreen: { flexGrow: 1, gap: 24, paddingBottom: 40, paddingHorizontal: 28, paddingTop: 72 },
  questionContent: { flexGrow: 1, paddingTop: 56 },
  progressRow: { flexDirection: "row", gap: 6 },
  progress: { flex: 1, height: 3 },
  eyebrow: { fontSize: 13, fontWeight: "700", letterSpacing: 2 },
  title: { fontSize: 36, fontWeight: "800", letterSpacing: -1.2, lineHeight: 41, marginTop: 14 },
  body: { fontSize: 16, lineHeight: 24, marginTop: 12 },
  input: {
    borderRadius: 12,
    borderWidth: 1,
    fontSize: 30,
    fontWeight: "700",
    marginTop: 40,
    paddingHorizontal: 18,
    paddingVertical: 18,
  },
  inline: { flexDirection: "row", gap: 12 },
  half: { flex: 1 },
  choiceList: { gap: 12, marginTop: 40 },
  choice: {
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 58,
    paddingHorizontal: 18,
  },
  choiceLabel: { fontSize: 17, fontWeight: "700" },
  error: { fontSize: 14, fontWeight: "600", marginTop: 20 },
  actions: { flexDirection: "row", gap: 12, paddingTop: 20 },
  backButton: {
    alignItems: "center",
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 56,
    paddingHorizontal: 22,
  },
  signOut: { alignItems: "center", justifyContent: "center", minHeight: 56, paddingHorizontal: 8 },
  nextButton: {
    alignItems: "center",
    borderRadius: 12,
    flex: 1,
    justifyContent: "center",
    minHeight: 56,
    paddingHorizontal: 16,
  },
  nextLabel: { color: "#001111", fontSize: 14, fontWeight: "900", letterSpacing: 1.5 },
  secondaryButton: {
    alignItems: "center",
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 56,
    marginTop: 12,
  },
  secondaryLabel: { fontSize: 13, fontWeight: "800", letterSpacing: 1.2 },
  result: { borderBottomWidth: 1, borderTopWidth: 1, gap: 18, paddingVertical: 24 },
  metric: { alignItems: "baseline", flexDirection: "row", justifyContent: "space-between" },
  metricValue: { fontSize: 30, fontWeight: "900" },
  metricUnit: { fontSize: 13, fontWeight: "700" },
  sectionLabel: { fontSize: 12, fontWeight: "700", letterSpacing: 1.8 },
  notice: { borderRadius: 12, borderWidth: 1, fontSize: 14, lineHeight: 21, padding: 16 },
});
