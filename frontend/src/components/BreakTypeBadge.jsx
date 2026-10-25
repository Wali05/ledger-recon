import { BREAK_HINTS, BREAK_LABELS, breakColor } from "../constants";

export default function BreakTypeBadge({ type }) {
  return (
    <span
      className="badge badge-type"
      style={{ "--badge": breakColor(type) }}
      title={BREAK_HINTS[type] || type}
    >
      {BREAK_LABELS[type] || type}
    </span>
  );
}
