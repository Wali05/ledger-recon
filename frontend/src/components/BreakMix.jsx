import { BREAK_HINTS, BREAK_LABELS, breakColor } from "../constants";
import { formatAmount, formatCompact } from "../format";

export default function BreakMix({ stats, activeType, onSelectType }) {
  const items = [...(stats?.breaks_by_type || [])].sort(
    (a, b) => b.count - a.count || a.break_type.localeCompare(b.break_type),
  );
  const largest = Math.max(1, ...items.map((item) => item.count));
  if (!items.length) return null;
  return (
    <section className="panel mix-panel" aria-labelledby="mix-title">
      <header className="panel-head">
        <h2 id="mix-title">Where the differences are</h2>
        <span className="panel-hint">Select a type to filter the queue</span>
      </header>
      <ul className="mix-list">
        {items.map((item) => {
          const active = activeType === item.break_type;
          const open = item.count - item.resolved_count;
          return (
            <li key={item.break_type}>
              <button
                className={`mix-row ${active ? "active" : ""}`}
                aria-pressed={active}
                title={BREAK_HINTS[item.break_type]}
                style={{ "--badge": breakColor(item.break_type) }}
                onClick={() => onSelectType(active ? "ALL" : item.break_type)}
              >
                <span className="mix-name">
                  <i aria-hidden="true" />
                  {BREAK_LABELS[item.break_type] || item.break_type}
                </span>
                <span className="mix-bar" aria-hidden="true">
                  <span style={{ width: `${(item.count / largest) * 100}%` }} />
                </span>
                <span className="mix-count">
                  {item.count}
                  {item.resolved_count > 0 && <small>{open} open</small>}
                </span>
                <span
                  className="mix-value"
                  title={`${formatAmount(item.open_value ?? "0")} open`}
                >
                  {formatCompact(item.open_value ?? "0")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
