import { Layers, TriangleAlert, CircleCheck, Percent } from "lucide-react";

// ─── Stats Cards ──────────────────────────────────────────────────────────────
export default function StatsCards({ stats }) {
  if (!stats) return null;
  const rate = stats.resolution_rate_pct ?? 0;
  return (
    <div className="stats-grid">
      <div className="stat-card" style={{ "--accent-color": "#4f6db8" }}>
        <div className="stat-head">
          <div className="stat-value">
            {stats.total_transactions_in_ledger?.toLocaleString() ?? "—"}
          </div>
          <div className="stat-icon">
            <Layers size={19} />
          </div>
        </div>
        <div className="stat-label">Ledger rows</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#c0442e" }}>
        <div className="stat-head">
          <div className="stat-value">
            {stats.total_breaks_detected?.toLocaleString() ?? "—"}
          </div>
          <div className="stat-icon">
            <TriangleAlert size={19} />
          </div>
        </div>
        <div className="stat-label">Detected breaks</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#3d8a5f" }}>
        <div className="stat-head">
          <div className="stat-value">
            {stats.total_breaks_resolved?.toLocaleString() ?? "—"}
          </div>
          <div className="stat-icon">
            <CircleCheck size={19} />
          </div>
        </div>
        <div className="stat-label">Resolved breaks</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#8560ad" }}>
        <div className="stat-head">
          <div className="stat-value">{rate.toFixed(1)}%</div>
          <div className="stat-icon">
            <Percent size={19} />
          </div>
        </div>
        <div className="stat-label">Resolution rate</div>
        <div className="progress-bar" style={{ marginTop: 12 }}>
          <div
            className="progress-fill"
            style={{
              width: `${Math.min(rate, 100)}%`,
              background: "linear-gradient(90deg,#8560ad,#6d4c93)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
