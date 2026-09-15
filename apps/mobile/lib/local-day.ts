export type TimezoneSyncStatus = "syncing" | "ready" | "unavailable";

export type LocalDayContext = {
  local_date: string;
  timezone: string;
};

export type EntryTiming = LocalDayContext & {
  eaten_at: string;
};

export class LocalDayUnavailable extends Error {
  constructor() {
    super("The device timezone is not synchronized.");
    this.name = "LocalDayUnavailable";
  }
}

/** Read the phone's timezone identifier. The API validates it before storage. */
export const deviceTimezone = (): string | null => {
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return typeof timezone === "string" && timezone.length > 0 ? timezone : null;
  } catch {
    return null;
  }
};

/** Format the phone's local calendar date without converting through UTC. */
export const localIsoDate = (now: Date): string => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

/** Parse an ISO calendar date without allowing UTC to shift the day. */
export const parseLocalIsoDate = (value: string): Date | null => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return localIsoDate(parsed) === value ? parsed : null;
};

/**
 * Build the fields every day-based request sends.
 *
 * Callers must pass the synchronized user timezone. Reading the device again
 * here could pair a newly changed timezone with the server's older value.
 */
export const localDayContext = (
  status: TimezoneSyncStatus,
  timezone: string,
  now = new Date(),
): LocalDayContext => {
  if (status !== "ready") throw new LocalDayUnavailable();
  return { local_date: localIsoDate(now), timezone };
};

/** Use the current local clock time on the selected calendar date. */
export const entryTimingForDate = (
  status: TimezoneSyncStatus,
  timezone: string,
  localDate: string,
  now = new Date(),
): EntryTiming => {
  if (status !== "ready") throw new LocalDayUnavailable();
  const date = parseLocalIsoDate(localDate);
  if (!date || localDate > localIsoDate(now)) throw new LocalDayUnavailable();
  date.setHours(now.getHours(), now.getMinutes(), now.getSeconds(), now.getMilliseconds());
  return { local_date: localDate, timezone, eaten_at: date.toISOString() };
};
