// Formatting uses decimal strings, so large financial amounts keep every digit.
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
export const formatDate = (value) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
