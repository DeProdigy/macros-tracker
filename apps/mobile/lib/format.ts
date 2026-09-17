/**
 * Turn an API macro value into something a person reads.
 *
 * The API serves calories, protein, and fiber from Django `DecimalField`
 * columns, and DRF renders those as strings with their full scale. A 130 kcal
 * shake arrives as `"130.00"`, so every screen that interpolated the raw value
 * printed "130.00 kcal".
 *
 * The bug predates MAC-61 and shipped on Today, the entry detail, and the photo
 * review. Nobody caught it because the test fixtures use short strings like
 * `"130"`, and a screenshot is what finally showed it.
 *
 * Rounding rather than trimming zeroes. These are estimates from a photo model
 * or a person typing a guess, and a tenth of a gram of fiber is false
 * precision either way. The stored value keeps its scale; only the display
 * loses it.
 */
export const macroValue = (value: string | number): string => {
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? Math.round(parsed).toLocaleString() : "0";
};
