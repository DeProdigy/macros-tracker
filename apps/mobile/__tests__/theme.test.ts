/**
 * Guards on the token system.
 *
 * The contrast block is the one that earns its keep. A colour edit six months
 * from now looks harmless in a diff and can quietly drop a label below the
 * readable threshold. A number in a test is the only thing that notices.
 */

import { describe, expect, it } from "@jest/globals";

import {
  colors,
  fontAssets,
  fontFamily,
  numeralScaleCap,
  space,
  tapTarget,
  type,
} from "@/lib/theme";

/**
 * Relative luminance, per WCAG 2.1.
 *
 * The sRGB values get linearised first. The eye is not linear in brightness,
 * and skipping that step gives ratios that look plausible and are wrong.
 */
const luminance = (hex: string): number => {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

const contrast = (a: string, b: string): number => {
  const [lighter, darker] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (lighter + 0.05) / (darker + 0.05);
};

describe("contrast", () => {
  // WCAG AA for body text. Large text may pass at 3:1, but holding one number
  // means nobody has to decide what counts as large.
  const AA = 4.5;

  const readable: Array<[string, string]> = [
    ["text", colors.text],
    ["textSecondary", colors.textSecondary],
    ["accent", colors.accent],
    ["warning", colors.warning],
    ["positive", colors.positive],
    ["protein", colors.protein],
    ["error", colors.error],
  ];

  it.each(readable)("%s passes AA on the page background", (_name, hex) => {
    expect(contrast(hex, colors.background)).toBeGreaterThanOrEqual(AA);
  });

  it.each(readable)("%s passes AA on a card", (_name, hex) => {
    expect(contrast(hex, colors.surface)).toBeGreaterThanOrEqual(AA);
  });

  it("keeps the primary button label readable on the accent fill", () => {
    expect(contrast(colors.background, colors.accent)).toBeGreaterThanOrEqual(AA);
  });

  /**
   * The one exemption, and it is deliberate.
   *
   * The approved mockups put this grey on entry timestamps. Alex chose the
   * artwork over the standard on 17 Sep 2026. The test asserts the value rather
   * than skipping it, so the exemption stays visible and stays this one colour.
   * If this fails, someone changed `textDim` without reopening the decision.
   */
  it("records that textDim is the accepted contrast exemption", () => {
    expect(contrast(colors.textDim, colors.background)).toBeLessThan(AA);
    expect(colors.textDim).toBe("#4a4e55");
  });
});

describe("tokens", () => {
  it("meets the iOS minimum tap target", () => {
    expect(tapTarget).toBeGreaterThanOrEqual(44);
  });

  it("caps numeral scaling without disabling it", () => {
    expect(numeralScaleCap).toBeGreaterThan(1);
    expect(numeralScaleCap).toBeLessThan(2);
  });

  it("keeps the spacing scale ascending", () => {
    const steps = [space.xs, space.sm, space.md, space.lg, space.xl, space.xxl];
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
  });

  it("gives every type role a family from the font map", () => {
    const families = Object.values(fontFamily) as string[];
    for (const role of Object.values(type)) {
      expect(families).toContain(role.fontFamily);
    }
  });

  it("loads every family the type scale asks for", () => {
    const loaded = Object.keys(fontAssets);
    for (const family of Object.values(fontFamily)) {
      expect(loaded).toContain(family);
    }
  });
});
