// Formatting uses decimal strings, so large financial amounts keep every digit.
// Amounts are never converted to JavaScript floating-point numbers.
export function formatAmount(value, currency) {
  if (value === null || value === undefined) return "—";
  const match = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return String(value);
  const [, sign, integer, fraction = ""] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  // Show cents; keep sub-cent digits only when they carry information.
  const shown = fraction.replace(/0+$/, "").padEnd(2, "0");
  return `${currency ? currency + " " : ""}${sign}${grouped}.${shown}`;
}

// Exact decimal string -> BigInt in ten-thousandths (four decimal places).
export function scaled(value) {
  const text = String(value ?? "0");
  const [whole, fraction = ""] = text.replace(/^-/, "").split(".");
  const amount =
    BigInt(whole || "0") * 10000n + BigInt(fraction.padEnd(4, "0").slice(0, 4));
  return text.startsWith("-") ? -amount : amount;
}

export function unscaled(amount) {
  const negative = amount < 0n;
  const digits = (negative ? -amount : amount).toString().padStart(5, "0");
  return `${negative ? "-" : ""}${digits.slice(0, -4)}.${digits.slice(-4)}`;
}

// Short form for headline figures ("2.15M"), rounded half up with BigInt.
export function formatCompact(value) {
  if (value === null || value === undefined) return "—";
  const amount = scaled(value);
  const size = amount < 0n ? -amount : amount;
  const units = [
    [10000n * 1_000_000_000n, "B"],
    [10000n * 1_000_000n, "M"],
    [10000n * 1_000n, "K"],
  ];
  for (const [unit, suffix] of units) {
    if (size >= unit) {
      const hundredths = (size * 100n + unit / 2n) / unit;
      const text = `${hundredths / 100n}.${String(hundredths % 100n).padStart(2, "0")}`;
      return `${amount < 0n ? "-" : ""}${text}${suffix}`;
    }
  }
  return formatAmount(unscaled(amount));
}

export const formatDate = (value) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";

export const formatDay = (value) =>
  value
    ? new Date(value).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      })
    : "—";

// Calendar days between two timestamps, compared as UTC dates like the matcher.
export function dayGap(a, b) {
  if (!a || !b) return null;
  const day = (value) => Math.floor(Date.parse(value) / 86_400_000);
  return Math.abs(day(a) - day(b));
}

export const formatPercent = (value, digits = 1) =>
  `${(Math.round(value * 10 ** digits) / 10 ** digits).toFixed(digits)}%`;
