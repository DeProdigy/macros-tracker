import { useGetDay } from "@macros/api-client";
import { Link, router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Image, Pressable, StyleSheet, View } from "react-native";

import { CalorieRing } from "@/components/calorie-ring";
import { DayPicker } from "@/components/day-picker";
import { MacroTile } from "@/components/macro-tile";
import { Button } from "@/components/ui/button";
import { Screen } from "@/components/ui/screen";
import {
  Body,
  Caption,
  ErrorText,
  Heading,
  Label,
  Muted,
  Numeral,
  Title,
} from "@/components/ui/text";
import { dayProgress } from "@/lib/day-progress";
import { macroValue } from "@/lib/format";
import { localIsoDate, parseLocalIsoDate } from "@/lib/local-day";
import { useSession } from "@/lib/session";
import { colors, radius, space, tapTarget } from "@/lib/theme";

export default function TodayScreen() {
  const session = useSession();
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const today = localIsoDate(new Date());
  const requestedDate = Array.isArray(params.date) ? params.date[0] : params.date;
  const localDate =
    requestedDate && parseLocalIsoDate(requestedDate) && requestedDate <= today
      ? requestedDate
      : today;
  const isToday = localDate === today;
  const [pickerVisible, setPickerVisible] = useState(false);
  const selectedDay = parseLocalIsoDate(localDate)!;
  const dayQuery = useGetDay(localDate, {
    query: { enabled: session.status === "signedIn" && session.timezoneStatus === "ready" },
  });
  if (session.status !== "signedIn") return null;
  const day = dayQuery.data?.status === 200 ? dayQuery.data.data : null;
  // Null when the day carries no target version. See lib/day-progress.ts for
  // why the current target is not substituted.
  const progress = day ? dayProgress(day) : null;

  return (
    <>
      <Screen
        contentStyle={styles.content}
        // The log action is a real footer rather than an absolutely positioned
        // button. The old version floated above the list, so the last entry
        // could scroll underneath it and stay unreachable.
        footer={
          <View style={styles.footer}>
            <Button
              onPress={() => router.push({ pathname: "/log-food", params: { date: localDate } })}
              title={isToday ? "Log food" : "Add to this day"}
            />
          </View>
        }
        scroll
      >
        <View style={styles.header}>
          <View>
            <Title>
              {isToday ? "Today" : selectedDay.toLocaleDateString([], { weekday: "long" })}
            </Title>
            <Pressable
              accessibilityLabel="Choose day"
              accessibilityRole="button"
              hitSlop={space.md}
              onPress={() => setPickerVisible(true)}
              style={styles.dateButton}
            >
              <Caption color={colors.accent}>
                {selectedDay
                  .toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" })
                  .toUpperCase()}
              </Caption>
            </Pressable>
          </View>
          <Link href="/settings" style={styles.settings}>
            <Caption color={colors.accent}>SETTINGS</Caption>
          </Link>
        </View>
        {session.timezoneStatus === "unavailable" ? (
          <ErrorText style={styles.message}>
            Timezone sync is unavailable. Reopen the app to try again.
          </ErrorText>
        ) : null}
        {progress ? (
          <>
            <View style={styles.ring}>
              <CalorieRing progress={progress} />
            </View>
            <View style={styles.tiles}>
              <MacroTile
                color={colors.protein}
                label="Protein"
                metColor={colors.positive}
                progress={progress.protein}
              />
              <MacroTile
                color={colors.protein}
                label="Fiber"
                metColor={colors.positive}
                progress={progress.fiber}
              />
            </View>
          </>
        ) : null}
        {day && !progress ? (
          // No target version on this day, so there is nothing to measure
          // against. Show what was eaten and no progress.
          <View style={styles.totals}>
            <Metric label="CALORIES" value={macroValue(day.calories)} />
            <Metric label="PROTEIN" value={`${macroValue(day.protein_g)} g`} />
            <Metric label="FIBER" value={`${macroValue(day.fiber_g)} g`} />
          </View>
        ) : null}
        <Label style={styles.section}>ENTRIES</Label>
        {dayQuery.isLoading ? <Muted>Loading your day...</Muted> : null}
        {dayQuery.isError ? (
          <ErrorText style={styles.message}>
            Could not load your day. Reopen the app to try again.
          </ErrorText>
        ) : null}
        {day && day.entries.length === 0 ? (
          <EmptyDay copy={emptyDayCopy(isToday, session.user.has_logged_food)} />
        ) : null}
        {day?.entries.map((entry) => (
          <Pressable
            accessibilityLabel={`Edit ${entry.description}`}
            accessibilityRole="button"
            key={entry.id}
            onPress={() =>
              router.push({ pathname: "/entry/[id]", params: { id: entry.id, date: localDate } })
            }
            style={styles.entry}
          >
            {entry.photo_url ? (
              <Image
                accessibilityLabel={`${entry.description} meal`}
                source={{ uri: entry.photo_url }}
                style={styles.entryPhoto}
              />
            ) : null}
            <View style={styles.entryMain}>
              <Body style={styles.entryName}>{entry.description}</Body>
              {/* `textDim` on a timestamp is the one accepted contrast
                  exemption. Alex chose the approved artwork over WCAG AA on
                  17 Sep 2026. See __tests__/theme.test.ts. */}
              <Caption color={colors.textDim}>
                {new Date(entry.eaten_at)
                  .toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
                  .toUpperCase()}
              </Caption>
            </View>
            <View style={styles.entryMacros}>
              <Body>{macroValue(entry.calories)} kcal</Body>
              <Caption>
                {macroValue(entry.protein_g)}p · {macroValue(entry.fiber_g)}f
              </Caption>
            </View>
          </Pressable>
        ))}
      </Screen>
      <DayPicker
        enabled={session.timezoneStatus === "ready"}
        onClose={() => setPickerVisible(false)}
        onSelect={(date) => {
          setPickerVisible(false);
          router.replace({ pathname: "/today", params: { date } });
        }}
        selectedDate={localDate}
        visible={pickerVisible}
      />
    </>
  );
}

type EmptyDayCopy = { title: string; body: string | null };

/**
 * Pick the copy for a day that holds no entries.
 *
 * The canonical flow doc asks for three empty days, not one. A first run has to
 * teach the next action. A normal empty Today must stay quiet, because the user
 * already knows what to do and a repeated lesson reads as noise. A past day has
 * to say that backfilling is still allowed, which is the part a user does not
 * guess.
 *
 * A pure function of two booleans, so the screen renders the right copy on the
 * first frame. Deriving it in an effect would paint the wrong state once and
 * then correct itself, which is visible as a flicker.
 *
 * `hasLoggedFood` comes from the session user, so it can lag the server by one
 * session. That is harmless here: it only ever flips false to true, and the
 * screens that log food update the cached user themselves.
 */
export function emptyDayCopy(isToday: boolean, hasLoggedFood: boolean): EmptyDayCopy {
  if (!isToday) {
    return {
      title: "Nothing logged this day",
      body: "You can still add food to this day.",
    };
  }
  if (!hasLoggedFood) {
    return {
      title: "Nothing logged yet",
      body: "Point the camera at your food. The app fills in the numbers.",
    };
  }
  return { title: "Nothing logged yet", body: null };
}

function EmptyDay({ copy }: { copy: EmptyDayCopy }) {
  return (
    <View style={styles.empty}>
      <Heading>{copy.title}</Heading>
      {copy.body ? <Muted style={styles.emptyBody}>{copy.body}</Muted> : null}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <View style={styles.metric}>
      <Label color={colors.textDim}>{label}</Label>
      <Numeral style={styles.metricValue}>{value}</Numeral>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: space.xl, paddingTop: space.xl },
  dateButton: { justifyContent: "center", minHeight: space.xl },
  empty: { alignItems: "center", paddingVertical: space.empty },
  emptyBody: { marginTop: space.sm, textAlign: "center" },
  entry: {
    alignItems: "center",
    borderColor: colors.border,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: tapTarget,
    paddingVertical: space.lg,
  },
  entryMacros: { alignItems: "flex-end", gap: space.xs },
  entryMain: { flex: 1 },
  entryName: { marginBottom: space.xs },
  entryPhoto: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    height: 52,
    marginRight: space.md,
    width: 52,
  },
  footer: { paddingHorizontal: space.xl, paddingTop: space.md },
  header: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  message: { marginTop: space.xl },
  metric: { flex: 1 },
  metricValue: { marginTop: space.xs },
  ring: { marginTop: space.xxl },
  section: { marginBottom: space.md, marginTop: space.section },
  settings: { minHeight: tapTarget, paddingTop: space.sm },
  tiles: { flexDirection: "row", gap: space.md, marginTop: space.xxl },
  totals: { flexDirection: "row", gap: space.sm, marginTop: space.xxl },
});
