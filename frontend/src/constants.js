// Colour carries meaning only: red = money that does not tie, amber = timing,
// green = suggested-rounding, violet = duplicates, slate = unclassified.
export const BREAK_COLORS = {
  AMOUNT_MISMATCH: "#c0392b",
  MISSING_INTERNAL: "#8e2a20",
  MISSING_EXTERNAL: "#e0705f",
  DUPLICATE: "#6b4fa0",
  TIMING_LAG: "#a26a00",
  FX_ROUNDING: "#1f7a55",
  UNKNOWN: "#6b7684",
};

export const BREAK_LABELS = {
  AMOUNT_MISMATCH: "Amount mismatch",
  MISSING_INTERNAL: "Missing in ledger",
  MISSING_EXTERNAL: "Missing at bank",
  DUPLICATE: "Duplicate",
  TIMING_LAG: "Timing lag",
  FX_ROUNDING: "FX rounding",
  UNKNOWN: "Unclassified",
};

export const BREAK_TYPE_OPTIONS = [
  "ALL",
  "AMOUNT_MISMATCH",
  "MISSING_INTERNAL",
  "MISSING_EXTERNAL",
  "DUPLICATE",
  "TIMING_LAG",
  "FX_ROUNDING",
  "UNKNOWN",
];
