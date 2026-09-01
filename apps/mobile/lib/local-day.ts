export type TimezoneSyncStatus = "syncing" | "ready" | "unavailable";

export type LocalDayContext = {
  local_date: string;
  timezone: string;
};

export class LocalDayUnavailable extends Error {
  constructor() {
    super("The device timezone is not synchronized.");
    this.name = "LocalDayUnavailable";
  }
}

/** Read the phone's IANA timezone name. An offset is not a safe substitute. */
export const deviceTimezone = (): string | null => {
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return (typeof timezone === "string" && timezone.includes("/")) || timezone === "UTC"
      ? timezone
      : null;
  } catch {
    return null;
  }
};

/** Format the phone's local calendar date without converting through UTC. */
export const localIsoDate = (now: Date): string => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
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
