import { beforeEach, describe, expect, it, jest } from "@jest/globals";
import { createTarget, getCurrentUser } from "@macros/api-client";

import { saveTargetVersion, TargetSavedButRefreshFailed } from "../lib/target-save";

jest.mock("@macros/api-client", () => ({
  createTarget: jest.fn(),
  getCurrentUser: jest.fn(),
}));

const mockCreate = createTarget as jest.MockedFunction<typeof createTarget>;
const mockMe = getCurrentUser as jest.MockedFunction<typeof getCurrentUser>;
const values = { calories: 2100, protein_g: 170, fiber_g: 30 };
const now = new Date(2026, 7, 31);

beforeEach(() => {
  jest.clearAllMocks();
  mockCreate.mockResolvedValue({ status: 201, data: {} } as never);
  mockMe.mockResolvedValue({
    status: 200,
    data: { onboarding_completed: true },
  } as never);
});

describe("saveTargetVersion", () => {
  it("writes the local effective date and returns the refreshed user", async () => {
    const user = await saveTargetVersion(values, now);

    expect(mockCreate).toHaveBeenCalledWith({ ...values, effective_from: "2026-08-31" });
    expect(user).toEqual({ onboarding_completed: true });
  });

  it("distinguishes a completed write from a failed refresh", async () => {
    mockMe.mockRejectedValue(new Error("offline"));

    await expect(saveTargetVersion(values, now)).rejects.toBeInstanceOf(
      TargetSavedButRefreshFailed,
    );
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });

  it("rejects an unexpected successful response shape before refreshing", async () => {
    mockCreate.mockResolvedValue({ status: 200, data: {} } as never);

    await expect(saveTargetVersion(values, now)).rejects.toThrow(
      "Unexpected target-create status: 200",
    );
    expect(mockMe).not.toHaveBeenCalled();
  });
});
