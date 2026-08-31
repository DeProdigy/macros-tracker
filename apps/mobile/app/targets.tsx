/**
 * The manual target editor, screen `6h` from doc 15.
 *
 * **Deliberately outside the `(app)` group.** That guard redirects anyone
 * without targets, and this is the screen where a user gets their first ones.
 * Inside `(app)` it would be hidden from every person who needs it, which is
 * the same trap that hid sign-out from un-onboarded users in MAC-47. A route
 * group guard hides everything in it, including the screens that are the way
 * out of the state being guarded.
 *
 * So it carries its own signed-out check, like `onboarding.tsx`.
 *
 * Two entry points, one component. From onboarding it is the hard gate's exit,
 * and saving is what sets `onboarding_completed` and opens the app. From
 * Settings it is an edit. The only difference is where the user came from, and
 * doc 15 says to keep them one component for exactly that reason.
 *
 * No orange "outside the suggested range" warning yet, and that is a decision
 * rather than an omission. The suggested range scales with body weight, the
 * server never sends it, and nothing has asked the user for a weight until
 * MAC-42. Copying the bands into TypeScript would put research numbers in two
 * places that drift apart in silence. It lands in slice 2, where the weight
 * exists. The absolute range still holds: the steppers clamp inside it and a
 * 400 renders if anything gets past them.
 */

import {
  ApiError,
  createTarget,
  getCurrentTarget,
  getCurrentUser,
  type TargetVersion,
} from "@macros/api-client";
import { Redirect, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { usePalette, type Palette } from "@/lib/palette";
import { useSession } from "@/lib/session";

/**
 * The flat half of the absolute range, mirrored from `targets/services.py`.
 *
 * Only the bounds that are constants on the server. Calories are 1,000 to 5,000
 * and fiber is 0 to 100 there, and neither reads the user.
 *
 * **Protein is missing on purpose.** Its absolute range scales with body weight
 * on the server, and the client has no weight to scale by. Clamping it to a
 * guessed number would be worse than not clamping: the server already skips
 * that check when the weight is missing, so a guess here would refuse values
 * the server would have accepted.
 *
 * These two are a stepper convenience, not the guard. The server rejects with a
 * 400 whatever the stepper allows, and the catch below renders it.
 */
const CALORIE_LIMITS = { min: 1000, max: 5000 };
const FIBER_LIMITS = { min: 0, max: 100 };

/**
 * What the steppers start on for a user who has never set targets.
 *
 * A neutral middle rather than a recommendation. The app cannot recommend
 * anything yet: Mifflin-St Jeor needs six answers and MAC-42 is the ticket that
 * asks for them. The copy on screen says so, because a number presented with no
 * hedge reads as advice.
 */
const STARTING_POINT = { calories: 2000, protein_g: 140, fiber_g: 30 };

const STEPS = { calories: 10, protein_g: 5, fiber_g: 1 };

type Field = keyof typeof STARTING_POINT;
type Values = Record<Field, number>;
type FieldErrors = Partial<Record<Field, string>>;

const clamp = (value: number, limits?: { min: number; max: number }) =>
  limits ? Math.min(Math.max(value, limits.min), limits.max) : Math.max(value, 0);

const LIMITS: Partial<Record<Field, { min: number; max: number }>> = {
  calories: CALORIE_LIMITS,
  fiber_g: FIBER_LIMITS,
};

/**
 * Pull per-field messages out of a 400 body.
 *
 * `reject_outside_absolute` raises with every failing field at once, and the
 * screen shows them all. A caller who fixes one, resubmits, and is told about
 * the next has been made to guess twice, which is the reasoning the server side
 * already carries.
 *
 * The generated type for a 400 is `data: void`, so the shape is not typed and
 * this reads it defensively. An unrecognised body falls through to the generic
 * message rather than rendering `undefined` at someone.
 */
const fieldErrorsFrom = (body: unknown): FieldErrors => {
  if (typeof body !== "object" || body === null) {
    return {};
  }

  const errors: FieldErrors = {};
  for (const field of Object.keys(STARTING_POINT) as Field[]) {
    const messages = (body as Record<string, unknown>)[field];
    if (Array.isArray(messages) && typeof messages[0] === "string") {
      errors[field] = messages[0];
    }
  }
  return errors;
};

export default function AdjustTargets() {
  const session = useSession();
  const palette = usePalette();
  const router = useRouter();

  const [values, setValues] = useState<Values>(STARTING_POINT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);

  // Seed from the current version when there is one. A 404 is the ordinary
  // first-run answer rather than a failure, so it falls through to the starting
  // point without telling the user anything went wrong.
  useEffect(() => {
    let cancelled = false;

    const seed = async () => {
      try {
        const response = await getCurrentTarget();
        if (!cancelled && response.status === 200) {
          const current: TargetVersion = response.data;
          setValues({
            calories: current.calories,
            protein_g: current.protein_g,
            fiber_g: current.fiber_g,
          });
        }
      } catch {
        // Keeps the starting point.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void seed();
    return () => {
      cancelled = true;
    };
  }, []);

  if (session.status === "loading") {
    return null;
  }

  if (session.status === "signedOut") {
    return <Redirect href="/login" />;
  }

  const step = (field: Field, direction: 1 | -1) => {
    setValues((current) => ({
      ...current,
      [field]: clamp(current[field] + STEPS[field] * direction, LIMITS[field]),
    }));
    // A stale error under a number the user just changed reads as a new
    // rejection of the new value.
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
  };

  const save = async () => {
    setSaving(true);
    setFieldErrors({});
    setFailure(null);

    try {
      await createTarget({
        ...values,
        // The user's local date, not the server's. Someone in Auckland setting
        // targets at 09:00 gets today, not yesterday.
        effective_from: new Date().toLocaleDateString("en-CA"),
      });

      // The server flips `onboarding_completed` on a user's first target, and
      // the route guard reads the session rather than the network. Without this
      // refetch the user saves targets and stays on this screen.
      const me = await getCurrentUser();
      if (me.status === 200) {
        session.updateUser(me.data);
      }

      router.replace("/today");
    } catch (error) {
      setSaving(false);

      if (error instanceof ApiError && error.status === 400) {
        const errors = fieldErrorsFrom(error.body);
        setFieldErrors(errors);
        if (Object.keys(errors).length === 0) {
          setFailure("That target was refused and the reason did not come through.");
        }
        return;
      }

      setFailure("Your targets weren't saved. Nothing changed, so try again in a minute.");
    }
  };

  if (loading) {
    return <View style={[styles.container, { backgroundColor: palette.background }]} />;
  }

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      style={[styles.container, { backgroundColor: palette.background }]}
    >
      <Text style={[styles.title, { color: palette.text }]}>Your call</Text>
      <Text style={[styles.body, { color: palette.secondaryText }]}>
        These are a starting point, not a recommendation. The app can work them out for you once it
        knows your height, weight, and what you are aiming for.
      </Text>

      <Row
        label="Calories"
        unit="kcal"
        value={values.calories}
        error={fieldErrors.calories}
        onStep={(direction) => step("calories", direction)}
        palette={palette}
      />
      <Row
        label="Protein"
        unit="g"
        value={values.protein_g}
        error={fieldErrors.protein_g}
        onStep={(direction) => step("protein_g", direction)}
        palette={palette}
      />
      <Row
        label="Fiber"
        unit="g"
        value={values.fiber_g}
        error={fieldErrors.fiber_g}
        onStep={(direction) => step("fiber_g", direction)}
        palette={palette}
      />

      {/* Doc 15 puts the append-only model in the copy, because it is the thing
          people form wrong assumptions about. Saving does not overwrite, and the
          button says so before the tap rather than a support page saying it
          after. */}
      <Text style={[styles.note, { color: palette.secondaryText }]}>
        Saving writes a new version. Days you have already logged keep the targets that were live at
        the time, so last week&apos;s progress never gets rewritten.
      </Text>

      {failure ? <Text style={[styles.failure, { color: palette.error }]}>{failure}</Text> : null}

      <Pressable
        accessibilityRole="button"
        disabled={saving}
        onPress={() => {
          void save();
        }}
        style={[styles.button, { backgroundColor: palette.accent }]}
      >
        <Text style={styles.buttonLabel}>{saving ? "Saving…" : "SAVE NEW VERSION"}</Text>
      </Pressable>
    </ScrollView>
  );
}

const Row = ({
  label,
  unit,
  value,
  error,
  onStep,
  palette,
}: {
  label: string;
  unit: string;
  value: number;
  error?: string;
  onStep: (direction: 1 | -1) => void;
  palette: Palette;
}) => (
  <View style={[styles.row, { borderColor: error ? palette.error : palette.hairline }]}>
    <Text style={[styles.rowLabel, { color: palette.dimText }]}>{label}</Text>

    <View style={styles.stepper}>
      <Pressable
        accessibilityLabel={`Decrease ${label.toLowerCase()}`}
        accessibilityRole="button"
        onPress={() => onStep(-1)}
        style={[styles.stepButton, { borderColor: palette.hairline }]}
      >
        <Text style={[styles.stepLabel, { color: palette.text }]}>−</Text>
      </Pressable>

      <Text style={[styles.value, { color: palette.accent }]}>
        {value}
        <Text style={[styles.unit, { color: palette.dimText }]}> {unit}</Text>
      </Text>

      <Pressable
        accessibilityLabel={`Increase ${label.toLowerCase()}`}
        accessibilityRole="button"
        onPress={() => onStep(1)}
        style={[styles.stepButton, { borderColor: palette.hairline }]}
      >
        <Text style={[styles.stepLabel, { color: palette.text }]}>+</Text>
      </Pressable>
    </View>

    {error ? <Text style={[styles.rowError, { color: palette.error }]}>{error}</Text> : null}
  </View>
);

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { gap: 16, paddingHorizontal: 24, paddingVertical: 48 },
  title: { fontSize: 30, fontWeight: "800", letterSpacing: -0.5 },
  body: { fontSize: 15, lineHeight: 22 },
  row: { borderRadius: 12, borderWidth: StyleSheet.hairlineWidth, gap: 8, padding: 16 },
  rowLabel: { fontSize: 12, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  rowError: { fontSize: 13, lineHeight: 18 },
  stepper: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  stepButton: {
    alignItems: "center",
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    height: 44,
    justifyContent: "center",
    width: 56,
  },
  stepLabel: { fontSize: 24, fontWeight: "600" },
  value: { fontSize: 34, fontWeight: "800" },
  unit: { fontSize: 15, fontWeight: "600" },
  note: { fontSize: 13, lineHeight: 19 },
  failure: { fontSize: 14, lineHeight: 20 },
  button: { alignItems: "center", borderRadius: 12, marginTop: 8, paddingVertical: 16 },
  buttonLabel: { color: "#ffffff", fontSize: 15, fontWeight: "800", letterSpacing: 1 },
});
