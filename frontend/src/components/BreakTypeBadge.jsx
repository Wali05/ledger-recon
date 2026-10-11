import { BREAK_COLORS, BREAK_LABELS } from "../constants";

export default function BreakTypeBadge({ type }) {
  return (
    <span
      className="badge badge-type"
      style={{ "--badge": BREAK_COLORS[type] }}
      title={type}
    >
      {BREAK_LABELS[type] || type}
    </span>
  );
}
