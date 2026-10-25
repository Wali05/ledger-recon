import { CONFIDENCE_HINTS, CONFIDENCE_LABELS } from "../constants";

// Three ticks, filled to the tier, so the level reads without colour alone.
const FILLED = { low: 1, medium: 2, high: 3 };

export default function ConfidenceBadge({ level, compact = false }) {
  if (!level) return <span className="confidence muted">—</span>;
  return (
    <span
      className={`confidence confidence-${level}`}
      title={CONFIDENCE_HINTS[level]}
    >
      <span className="confidence-ticks" aria-hidden="true">
        {[1, 2, 3].map((tick) => (
          <i key={tick} className={tick <= FILLED[level] ? "on" : ""} />
        ))}
      </span>
      {compact ? (
        <span className="sr-only">{CONFIDENCE_LABELS[level]} confidence</span>
      ) : (
        CONFIDENCE_LABELS[level]
      )}
    </span>
  );
}
