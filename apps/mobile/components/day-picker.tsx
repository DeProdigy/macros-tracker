import { useGetDays } from "@macros/api-client";
import { useEffect, useMemo, useState } from "react";
import { Modal, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Body, Caption, ErrorText, Heading, Label } from "@/components/ui/text";
import { localIsoDate, parseLocalIsoDate } from "@/lib/local-day";
import { colors, radius, space, tapTarget } from "@/lib/theme";

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
  // A modal sits outside the screen's `Screen` wrapper, so it reads the inset
  // itself. Without this the Done row sits under the home indicator.
  const insets = useSafeAreaInsets();
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
        <View style={[styles.sheet, { paddingBottom: space.md + insets.bottom }]}>
          <View style={styles.heading}>
            <Pressable
              accessibilityLabel="Previous month"
              accessibilityRole="button"
              onPress={() =>
                setMonth((value) => new Date(value.getFullYear(), value.getMonth() - 1, 1))
              }
            >
              <Heading color={colors.accent} style={styles.arrow}>
                ‹
              </Heading>
            </Pressable>
            <Heading>{month.toLocaleDateString([], { month: "long", year: "numeric" })}</Heading>
            <Pressable
              accessibilityLabel="Next month"
              accessibilityRole="button"
              disabled={queryMonth >= currentMonth}
              onPress={() =>
                setMonth((value) => new Date(value.getFullYear(), value.getMonth() + 1, 1))
              }
            >
              <Heading
                color={colors.accent}
                style={[styles.arrow, queryMonth >= currentMonth ? styles.arrowDisabled : null]}
              >
                ›
              </Heading>
            </Pressable>
          </View>
          <View style={styles.grid}>
            {weekdays.map((weekday, index) => (
              <Label key={`${weekday}-${index}`} style={styles.weekday}>
                {weekday}
              </Label>
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
                  style={[styles.day, selectedDay ? styles.daySelected : null]}
                >
                  <Body
                    color={selectedDay ? colors.background : colors.text}
                    style={future ? styles.dayFuture : null}
                  >
                    {date.getDate()}
                  </Body>
                  {loggedDates.has(dateValue) ? (
                    <View
                      accessibilityLabel="Contains logged food"
                      style={[
                        styles.dot,
                        { backgroundColor: selectedDay ? colors.background : colors.accent },
                      ]}
                    />
                  ) : null}
                </Pressable>
              );
            })}
          </View>
          {daysQuery.isError ? (
            <ErrorText style={styles.error}>Could not load logged-day markers.</ErrorText>
          ) : null}
          <Pressable accessibilityRole="button" onPress={onClose} style={styles.done}>
            <Caption color={colors.accent}>DONE</Caption>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  arrow: { minWidth: tapTarget, textAlign: "center" },
  arrowDisabled: { opacity: 0.3 },
  backdrop: { backgroundColor: "rgba(0, 0, 0, 0.55)", flex: 1, justifyContent: "flex-end" },
  day: {
    alignItems: "center",
    borderRadius: radius.full,
    height: tapTarget,
    justifyContent: "center",
    width: "14.285%",
  },
  dayFuture: { opacity: 0.3 },
  daySelected: { backgroundColor: colors.accent },
  done: {
    alignItems: "center",
    justifyContent: "center",
    marginTop: space.md,
    minHeight: tapTarget,
  },
  dot: { borderRadius: 2, bottom: 5, height: 4, position: "absolute", width: 4 },
  error: { marginTop: space.md, textAlign: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", marginTop: space.lg },
  heading: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: space.xl,
  },
  weekday: { textAlign: "center", width: "14.285%" },
});
