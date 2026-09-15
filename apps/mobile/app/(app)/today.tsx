import { useGetDay } from "@macros/api-client";
import { Link, router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { DayPicker } from "@/components/day-picker";
import { localIsoDate, parseLocalIsoDate } from "@/lib/local-day";
import { usePalette } from "@/lib/palette";
import { useSession } from "@/lib/session";

export default function TodayScreen() {
  const session = useSession();
  const palette = usePalette();
  const params = useLocalSearchParams<{ date?: string | string[] }>();
  const today = localIsoDate(new Date());
  const requestedDate = Array.isArray(params.date) ? params.date[0] : params.date;
  const localDate =
    requestedDate && parseLocalIsoDate(requestedDate) && requestedDate <= today
      ? requestedDate
      : today;
  const [pickerVisible, setPickerVisible] = useState(false);
  const selectedDay = parseLocalIsoDate(localDate)!;
  const dayQuery = useGetDay(localDate, {
    query: { enabled: session.status === "signedIn" && session.timezoneStatus === "ready" },
  });
  if (session.status !== "signedIn") return null;
  const day = dayQuery.data?.status === 200 ? dayQuery.data.data : null;

  return (
    <View style={[styles.page, { backgroundColor: palette.background }]}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={[styles.title, { color: palette.text }]}>
              {localDate === today
                ? "Today"
                : selectedDay.toLocaleDateString([], { weekday: "long" })}
            </Text>
            <Pressable
              accessibilityLabel="Choose day"
              accessibilityRole="button"
              onPress={() => setPickerVisible(true)}
            >
              <Text style={[styles.date, { color: palette.accent }]}>
                {selectedDay.toLocaleDateString([], {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </Text>
            </Pressable>
          </View>
          <Link href="/settings" style={{ color: palette.accent }}>
            Settings
          </Link>
        </View>
        {session.timezoneStatus === "unavailable" ? (
          <Text accessibilityRole="alert" style={[styles.message, { color: palette.error }]}>
            Timezone sync is unavailable. Reopen the app to try again.
          </Text>
        ) : null}
        {day ? (
          <View style={styles.totals}>
            <Metric label="CALORIES" value={day.calories} color={palette.text} />
            <Metric label="PROTEIN" value={`${day.protein_g} g`} color={palette.text} />
            <Metric label="FIBER" value={`${day.fiber_g} g`} color={palette.text} />
          </View>
        ) : null}
        <Text style={[styles.section, { color: palette.secondaryText }]}>ENTRIES</Text>
        {dayQuery.isLoading ? (
          <Text style={{ color: palette.secondaryText }}>Loading your day...</Text>
        ) : null}
        {dayQuery.isError ? (
          <Text accessibilityRole="alert" style={[styles.message, { color: palette.error }]}>
            Could not load your day. Reopen the app to try again.
          </Text>
        ) : null}
        {day && day.entries.length === 0 ? (
          <View style={styles.empty}>
            <Text style={[styles.emptyTitle, { color: palette.text }]}>Nothing logged yet</Text>
            <Text style={[styles.emptyBody, { color: palette.secondaryText }]}>
              Add your first food and it will appear here.
            </Text>
          </View>
        ) : null}
        {day?.entries.map((entry) => (
          <Pressable
            accessibilityLabel={`Edit ${entry.description}`}
            accessibilityRole="button"
            key={entry.id}
            onPress={() =>
              router.push({ pathname: "/entry/[id]", params: { id: entry.id, date: localDate } })
            }
            style={[styles.entry, { borderColor: palette.hairline }]}
          >
            {entry.photo_url ? (
              <Image
                accessibilityLabel={`${entry.description} meal`}
                source={{ uri: entry.photo_url }}
                style={styles.entryPhoto}
              />
            ) : null}
            <View style={styles.entryMain}>
              <Text style={[styles.entryName, { color: palette.text }]}>{entry.description}</Text>
              <Text style={{ color: palette.dimText }}>
                {new Date(entry.eaten_at).toLocaleTimeString([], {
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </Text>
            </View>
            <View style={styles.entryMacros}>
              <Text style={{ color: palette.text }}>{entry.calories} kcal</Text>
              <Text style={{ color: palette.secondaryText }}>
                {entry.protein_g}p · {entry.fiber_g}f
              </Text>
            </View>
          </Pressable>
        ))}
      </ScrollView>
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push({ pathname: "/log-food", params: { date: localDate } })}
        style={[styles.log, { backgroundColor: palette.accent }]}
      >
        <Text style={styles.logText}>LOG FOOD</Text>
      </Pressable>
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
    </View>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  content: { paddingBottom: 130, paddingHorizontal: 24, paddingTop: 68 },
  header: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  title: { fontSize: 36, fontWeight: "900" },
  date: { fontSize: 13, marginTop: 4 },
  message: { marginTop: 24 },
  totals: { flexDirection: "row", gap: 10, marginTop: 36 },
  metric: { flex: 1 },
  metricLabel: { color: "#777", fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  metricValue: { fontSize: 20, fontWeight: "900", marginTop: 7 },
  section: { fontSize: 11, fontWeight: "800", letterSpacing: 1.5, marginBottom: 14, marginTop: 42 },
  empty: { alignItems: "center", paddingVertical: 64 },
  emptyTitle: { fontSize: 20, fontWeight: "800" },
  emptyBody: { marginTop: 8 },
  entry: {
    alignItems: "center",
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 18,
  },
  entryName: { fontSize: 17, fontWeight: "700" },
  entryMain: { flex: 1 },
  entryPhoto: { borderRadius: 8, height: 52, marginRight: 12, width: 52 },
  entryMacros: { alignItems: "flex-end", gap: 4 },
  log: {
    alignItems: "center",
    borderRadius: 12,
    bottom: 34,
    justifyContent: "center",
    left: 24,
    minHeight: 58,
    position: "absolute",
    right: 24,
  },
  logText: { color: "#001018", fontWeight: "900", letterSpacing: 1.2 },
});
