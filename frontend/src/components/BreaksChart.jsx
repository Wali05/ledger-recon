import { BREAK_COLORS, BREAK_LABELS } from "../constants";

export default function BreaksChart({ stats }) {
  const items = [...(stats?.breaks_by_type || [])].sort(
    (a, b) => b.count - a.count,
  );
  const total = items.reduce((sum, item) => sum + item.count, 0);
  if (!total) return null;
  return (
    <section className="chart-card" aria-labelledby="breakdown-title">
      <h2 id="breakdown-title" className="chart-title">
        What kind of breaks
      </h2>
      <div className="mix-bar" aria-hidden="true">
        {items.map((item) => (
          <span
            key={item.break_type}
            style={{
              width: `${(item.count / total) * 100}%`,
              background: BREAK_COLORS[item.break_type],
            }}
          />
        ))}
      </div>
      <dl className="breakdown-list">
        {items.map((item) => (
          <div key={item.break_type}>
            <dt className="breakdown-label">
              <i style={{ background: BREAK_COLORS[item.break_type] }} />
              {BREAK_LABELS[item.break_type] || item.break_type}
            </dt>
            <dd className="breakdown-count">
              {item.count}
              {item.resolved_count > 0 && (
                <span>{item.resolved_count} resolved</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
