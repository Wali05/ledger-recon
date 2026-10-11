// Formatting uses decimal strings, so large financial amounts keep every digit.
export function formatAmount(value, currency) {
  if (value === null || value === undefined) return "—";
  const match = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return String(value);
  const [, sign, integer, fraction = ""] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${currency ? currency + " " : ""}${sign}${grouped}.${fraction.padEnd(4, "0")}`;
}
export const formatDate = (value) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "—";
