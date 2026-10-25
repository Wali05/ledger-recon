import { formatAmount, formatCompact, formatPercent } from "../format";

function Meter({ value, label, tone }) {
  const width = Math.max(0, Math.min(value, 100));
  return (
    <div
      className={`meter ${tone || ""}`}
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(width)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${width}%` }} />
    </div>
  );
}

export default function Overview({ stats }) {
  if (!stats)
    return <section className="overview skeleton" aria-hidden="true" />;
  const count = (value) => (value ?? 0).toLocaleString();
  const ledger = stats.total_transactions_in_ledger ?? 0;
  const total = stats.total_breaks_detected ?? 0;
  const resolved = stats.total_breaks_resolved ?? 0;
  const open = Math.max(total - resolved, 0);
  const tied = Math.max(ledger - (stats.ledger_rows_in_breaks ?? 0), 0);
  const tiedRate = ledger ? (tied / ledger) * 100 : 0;
  const levels = Object.fromEntries(
    (stats.open_by_confidence || []).map((row) => [
      row.confidence,
      row.open_count,
    ]),
  );
  const attention = (levels.low || 0) + (levels.medium || 0);
  return (
    <section className="overview" aria-label="Summary">
      <div className="stat-card">
        <div className="stat-label">Tied out automatically</div>
        <div className="stat-value tie">
          {ledger ? formatPercent(tiedRate) : "—"}
        </div>
        <Meter value={tiedRate} label="Ledger rows tied out" tone="tie" />
        <div className="stat-note">
          {count(tied)} of {count(ledger)} ledger rows · against{" "}
          {count(stats.total_transactions_in_statement)} bank lines
        </div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Open breaks</div>
        <div className="stat-value">{count(open)}</div>
        <Meter value={stats.resolution_rate_pct ?? 0} label="Breaks reviewed" />
        <div className="stat-note">
          {count(resolved)} of {count(total)} reviewed (
          {formatPercent(stats.resolution_rate_pct ?? 0)})
        </div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Open exposure</div>
        <div
          className="stat-value money"
          title={formatAmount(stats.open_value ?? "0")}
        >
          {formatCompact(stats.open_value ?? "0")}
        </div>
        <div className="stat-note">
          Money that open breaks leave unexplained: the difference for amount
          breaks, the full amount otherwise.
        </div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Needs a closer look</div>
        <div className="stat-value attention">{count(attention)}</div>
        <ul className="confidence-split" aria-label="Open breaks by confidence">
          {["low", "medium", "high"].map((level) => (
            <li key={level} className={`confidence-${level}`}>
              <i aria-hidden="true" />
              {level} <strong>{count(levels[level])}</strong>
            </li>
          ))}
        </ul>
        <div className="stat-note">
          Open breaks the rules are least sure of.
        </div>
      </div>
    </section>
  );
}
