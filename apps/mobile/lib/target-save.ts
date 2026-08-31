import { createTarget, getCurrentUser, type Targets, type User } from "@macros/api-client";

/** The target row exists, but the client could not refresh its user snapshot. */
export class TargetSavedButRefreshFailed extends Error {
  constructor() {
    super("Target saved, but user refresh failed.");
    this.name = "TargetSavedButRefreshFailed";
  }
}

/** Format the phone's local calendar date without converting through UTC. */
export const localIsoDate = (now: Date): string => {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

/**
 * Create one append-only target version and return the refreshed user.
 *
 * The write and refresh are deliberately one helper but two outcomes. Once
 * createTarget returns 201, a later refresh failure must never be described as
 * an unsaved write or offered as retryable. Retrying is not idempotent and
 * would create a second TargetVersion for the same user action.
 */
export const saveTargetVersion = async (values: Targets, now = new Date()): Promise<User> => {
  const created = await createTarget({ ...values, effective_from: localIsoDate(now) });
  if (created.status !== 201) {
    throw new Error(`Unexpected target-create status: ${created.status}`);
  }

  try {
    const response = await getCurrentUser();
    if (response.status === 200) return response.data;
  } catch {
    // Convert every refresh failure into the same post-save state.
  }

  throw new TargetSavedButRefreshFailed();
};
