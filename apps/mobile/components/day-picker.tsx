import { useGetDays } from "@macros/api-client";
import { useEffect, useMemo, useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { localIsoDate, parseLocalIsoDate } from "@/lib/local-day";
import { usePalette } from "@/lib/palette";

type DayPickerProps = {
  enabled: boolean;
  onClose: () => void;
  onSelect: (date: string) => void;
  selectedDate: string;
  visible: boolean;
};

const weekdays = ["S", "M", "T", "W", "T", "F", "S"];

const monthValue = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;

export function DayPicker({ enabled, onClose, onSelect, selectedDate, visible }: DayPickerProps) {
  const palette = usePalette();
  const selected = parseLocalIsoDate(selectedDate) ?? new Date();
  const [month, setMonth] = useState(
    () => new Date(selected.getFullYear(), selected.getMonth(), 1),
  );
  const today = localIsoDate(new Date());
  const currentMonth = monthValue(new Date());
  const queryMonth = monthValue(month);
  const daysQuery = useGetDays({ month: queryMonth }, { query: { enabled: enabled && visible } });

  useEffect(() => {
    if (visible) setMonth(new Date(selected.getFullYear(), selected.getMonth(), 1));
  }, [selectedDate, visible]);

  const loggedDates = useMemo(
    () =>
      new Set(
        daysQuery.data?.status === 200 ? daysQuery.data.data.map((day) => day.local_date) : [],
      ),
    [daysQuery.data],
  );
  const leading = month.getDay();
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells = Array.from({ length: leading + count }, (_, index) =>
    index < leading ? null : new Date(month.getFullYear(), month.getMonth(), index - leading + 1),
  );

  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible={visible}>
      <View style={styles.backdrop}>
        <View style={[styles.sheet, { backgroundColor: palette.background }]}>
          <View style={styles.heading}>
            <Pressable
              accessibilityLabel="Previous month"
              accessibilityRole="button"
              onPress={() =>
                setMonth((value) => new Date(value.getFullYear(), value.getMonth() - 1, 1))
              }
            >
              <Text style={[styles.arrow, { color: palette.accent }]}>‹</Text>
            </Pressable>
            <Text style={[styles.month, { color: palette.text }]}>
              {month.toLocaleDateString([], { month: "long", year: "numeric" })}
            </Text>
            <Pressable
              accessibilityLabel="Next month"
              accessibilityRole="button"
              disabled={queryMonth >= currentMonth}
              onPress={() =>
                setMonth((value) => new Date(value.getFullYear(), value.getMonth() + 1, 1))
              }
            >
              <Text
                style={[
                  styles.arrow,
                  { color: palette.accent, opacity: queryMonth >= currentMonth ? 0.3 : 1 },
                ]}
              >
                ›
              </Text>
            </Pressable>
          </View>
          <View style={styles.grid}>
            {weekdays.map((weekday, index) => (
              <Text
                key={`${weekday}-${index}`}
                style={[styles.weekday, { color: palette.secondaryText }]}
              >
                {weekday}
              </Text>
            ))}
            {cells.map((date, index) => {
              if (!date) return <View key={`empty-${index}`} style={styles.day} />;
              const dateValue = localIsoDate(date);
              const selectedDay = dateValue === selectedDate;
              const future = dateValue > today;
              return (
                <Pressable
                  accessibilityLabel={`Choose ${date.toLocaleDateString([], {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}`}
                  accessibilityRole="button"
                  disabled={future}
                  key={dateValue}
                  onPress={() => onSelect(dateValue)}
                  style={[styles.day, selectedDay ? { backgroundColor: palette.accent } : null]}
                >
                  <Text
                    style={{
                      color: selectedDay ? palette.background : palette.text,
                      opacity: future ? 0.3 : 1,
                    }}
                  >
                    {date.getDate()}
                  </Text>
                  {loggedDates.has(dateValue) ? (
                    <View
                      accessibilityLabel="Contains logged food"
                      style={[
                        styles.dot,
                        { backgroundColor: selectedDay ? palette.background : palette.accent },
                      ]}
                    />
                  ) : null}
                </Pressable>
              );
            })}
          </View>
          {daysQuery.isError ? (
            <Text accessibilityRole="alert" style={[styles.error, { color: palette.error }]}>
              Could not load logged-day markers.
            </Text>
          ) : null}
          <Pressable accessibilityRole="button" onPress={onClose} style={styles.done}>
            <Text style={{ color: palette.accent, fontWeight: "800" }}>DONE</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: "rgba(0, 0, 0, 0.55)", flex: 1, justifyContent: "flex-end" },
  sheet: { borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24 },
  heading: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  arrow: { fontSize: 36, minWidth: 42, textAlign: "center" },
  month: { fontSize: 18, fontWeight: "800" },
  grid: { flexDirection: "row", flexWrap: "wrap", marginTop: 18 },
  weekday: { fontSize: 11, fontWeight: "800", textAlign: "center", width: "14.285%" },
  day: {
    alignItems: "center",
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    width: "14.285%",
  },
  dot: { borderRadius: 2, bottom: 5, height: 4, position: "absolute", width: 4 },
  error: { marginTop: 12, textAlign: "center" },
  done: { alignItems: "center", minHeight: 48, justifyContent: "center", marginTop: 12 },
});
