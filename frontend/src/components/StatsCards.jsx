export default function StatsCards({ stats }) {
  if (!stats) return null;
  const total = stats.total_breaks_detected ?? 0;
  const resolved = stats.total_breaks_resolved ?? 0;
  const open = Math.max(total - resolved, 0);
  const rate = stats.resolution_rate_pct ?? 0;
  const count = (value) => value?.toLocaleString() ?? "—";
  return (
    <section className="stats-grid" aria-label="Summary">
      <div className="stat-card">
        <div className="stat-label">Ledger rows</div>
        <div className="stat-value">
          {count(stats.total_transactions_in_ledger)}
        </div>
        <div className="stat-note">
          against {count(stats.total_transactions_in_statement)} statement rows
        </div>
      </div>
      <div className="stat-card breaks">
        <div className="stat-label">Breaks found</div>
        <div className="stat-value">{count(total)}</div>
        <div className="stat-note">
          {stats.breaks_by_type?.length || 0} kinds of difference
        </div>
      </div>
      <div className="stat-card resolved">
        <div className="stat-label">Resolved</div>
        <div className="stat-value">{count(resolved)}</div>
        <div
          className="progress-bar"
          role="progressbar"
          aria-label="Breaks resolved"
          aria-valuenow={Math.round(rate)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="progress-fill"
            style={{ width: `${Math.min(rate, 100)}%` }}
          />
        </div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Still open</div>
        <div className="stat-value">{count(open)}</div>
        <div className="stat-note">{rate.toFixed(1)}% reviewed</div>
      </div>
    </section>
  );
}
