import { BREAK_COLORS } from "../constants";

export default function BreaksChart({ stats }) {
  const items = stats?.breaks_by_type || [];
  if (!items.length) return null;
  const largest = Math.max(...items.map((item) => item.count), 1);
  return (
    <section className="chart-card" aria-labelledby="breakdown-title">
      <h2 id="breakdown-title" className="chart-title">
        Breaks by type
      </h2>
      <dl className="breakdown-list">
        {items.map((item) => (
          <div key={item.break_type}>
            <dt className="breakdown-label">
              {item.break_type.replaceAll("_", " ")}
            </dt>
            <dd className="breakdown-count">
              <strong>{item.count}</strong>
              <span>{item.resolved_count} resolved</span>
            </dd>
            <div className="breakdown-track" aria-hidden="true">
              <div
                className="breakdown-fill"
                style={{
                  width: `${(item.count / largest) * 100}%`,
                  background: BREAK_COLORS[item.break_type] || "#9a9384",
                }}
              />
            </div>
          </div>
        ))}
      </dl>
    </section>
  );
}
