// Colour carries meaning only: red = money that does not tie, amber = timing,
// green = suggested rounding, violet = duplicates, blue = reference only,
// teal = grouped settlement, slate = unclassified. Each theme defines the
// matching --type-* variable so the palette stays legible in light and dark.
export const BREAK_TYPES = [
  "AMOUNT_MISMATCH",
  "MISSING_INTERNAL",
  "MISSING_EXTERNAL",
  "DUPLICATE",
  "TIMING_LAG",
  "FX_ROUNDING",
  "REFERENCE_MISMATCH",
  "SPLIT_SETTLEMENT",
  "UNKNOWN",
];

export const BREAK_LABELS = {
  AMOUNT_MISMATCH: "Amount mismatch",
  MISSING_INTERNAL: "Missing in ledger",
  MISSING_EXTERNAL: "Missing at bank",
  DUPLICATE: "Duplicate",
  TIMING_LAG: "Timing lag",
  FX_ROUNDING: "FX rounding",
  REFERENCE_MISMATCH: "Reference mismatch",
  SPLIT_SETTLEMENT: "Split settlement",
  UNKNOWN: "Unclassified",
};

export const BREAK_HINTS = {
  AMOUNT_MISMATCH: "Paired rows disagree on the amount",
  MISSING_INTERNAL: "On the bank statement only",
  MISSING_EXTERNAL: "In the ledger only",
  DUPLICATE: "An extra copy of a transaction ID",
  TIMING_LAG: "Same amount, booked 1–3 days apart",
  FX_ROUNDING: "A few cents on a foreign-currency row",
  REFERENCE_MISMATCH: "Same amount and day, bank used its own reference",
  SPLIT_SETTLEMENT: "One line equals the exact sum of several",
  UNKNOWN: "The rules cannot explain the pair",
};

export const breakColor = (type) =>
  `var(--type-${(BREAK_TYPES.includes(type) ? type : "UNKNOWN").toLowerCase()})`;

export const CONFIDENCE_LABELS = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const CONFIDENCE_HINTS = {
  low: "Several rows compete or another combination fits. Check first.",
  medium: "A suggestion the evidence supports, worth a second look.",
  high: "The evidence is unambiguous.",
};
