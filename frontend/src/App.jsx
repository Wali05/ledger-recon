import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  triggerReconciliation, getJobStatus, getBreaks, getStats, resolveBreak, getBreak,
  uploadLedger, uploadStatement, explainBreakWithAI, exportBreaks
} from "./api";
import "./index.css";

// ─── Constants ────────────────────────────────────────────────────────────────
const BREAK_COLORS = {
  AMOUNT_MISMATCH: "#f59e0b",
  MISSING_INTERNAL: "#ef4444",
  MISSING_EXTERNAL: "#f87171",
  DUPLICATE: "#8b5cf6",
  TIMING_LAG: "#06b6d4",
  FX_ROUNDING: "#10b981",
  UNKNOWN: "#64748b",
};

const BREAK_TYPE_OPTIONS = [
  "ALL",
  "AMOUNT_MISMATCH",
  "MISSING_INTERNAL",
  "MISSING_EXTERNAL",
  "DUPLICATE",
  "TIMING_LAG",
  "FX_ROUNDING",
  "UNKNOWN",
];

// ─── Toast ───────────────────────────────────────────────────────────────────
function Toast({ toasts }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.type}`}>
          <span>{t.type === "success" ? "✓" : "✗"}</span>
          {t.message}
        </div>
      ))}
    </div>
  );
}

// ─── Break Type Badge ─────────────────────────────────────────────────────────
function BreakTypeBadge({ type }) {
  return <span className={`badge badge-${type}`}>{type?.replace(/_/g, " ")}</span>;
}

// ─── Break Detail Modal ───────────────────────────────────────────────────────
function BreakDetailModal({ breakId, onClose, onResolved, addToast }) {
  const [br, setBr] = useState(null);
  const [resolving, setResolving] = useState(false);
  const [aiExplanation, setAiExplanation] = useState(null);
  const [askingAi, setAskingAi] = useState(false);

  useEffect(() => {
    let active = true;
    getBreak(breakId).then((data) => {
      if (active) {
        setBr(data);
        if (data.ai_explanation) {
          setAiExplanation(data.ai_explanation);
        }
      }
    });
    return () => { active = false; };
  }, [breakId]);

  const handleResolve = async () => {
    setResolving(true);
    try {
      await resolveBreak(breakId);
      setBr({ ...br, resolved: true, resolved_at: new Date().toISOString() });
      addToast("Break resolved", "success");
      if (onResolved) onResolved();
    } catch (e) {
      addToast("Failed to resolve break", "error");
    } finally {
      setResolving(false);
    }
  };

  const handleAskAi = async () => {
    setAskingAi(true);
    try {
      const result = await explainBreakWithAI(breakId);
      setAiExplanation(result.explanation);
      setBr({ ...br, ai_explanation: result.explanation });
    } catch (e) {
      addToast(e.message || "Failed to get AI explanation", "error");
    } finally {
      setAskingAi(false);
    }
  };

  const fmt = (v) => (v !== null && v !== undefined ? String(v) : "—");
  const fmtAmt = (v) =>
    v !== null && v !== undefined ? `$${parseFloat(v).toFixed(4)}` : "—";
  const fmtDate = (v) =>
    v ? new Date(v).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : "—";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Break Detail</span>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {!br ? (
            <div className="loading-wrap"><div className="spinner" /></div>
          ) : (
            <>
              <div style={{ marginBottom: 20 }}>
                <BreakTypeBadge type={br.break_type} />
                {br.resolved && (
                  <span className="badge badge-resolved" style={{ marginLeft: 8 }}>Resolved</span>
                )}
              </div>
              <div className="detail-grid">
                <div className="detail-item">
                  <label>Transaction ID</label>
                  <span style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>
                    {br.transaction_id}
                  </span>
                </div>
                <div className="detail-item">
                  <label>Break ID</label>
                  <span style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>
                    {br.break_id}
                  </span>
                </div>
                <div className="detail-item">
                  <label>Internal Amount</label>
                  <span>{fmtAmt(br.internal_amount)}</span>
                </div>
                <div className="detail-item">
                  <label>External Amount</label>
                  <span>{fmtAmt(br.external_amount)}</span>
                </div>
                <div className="detail-item">
                  <label>Delta</label>
                  <span
                    style={{
                      color:
                        parseFloat(br.delta_amount) > 0
                          ? "var(--accent-green)"
                          : parseFloat(br.delta_amount) < 0
                          ? "var(--accent-red)"
                          : "inherit",
                      fontWeight: 600,
                    }}
                  >
                    {br.delta_amount !== null && br.delta_amount !== undefined
                      ? `${parseFloat(br.delta_amount) >= 0 ? "+" : ""}${parseFloat(br.delta_amount).toFixed(4)}`
                      : "—"}
                  </span>
                </div>
                <div className="detail-item">
                  <label>Detected At</label>
                  <span>{fmtDate(br.detected_at)}</span>
                </div>
                <div className="detail-item">
                  <label>Internal Date</label>
                  <span>{fmtDate(br.internal_timestamp)}</span>
                </div>
                <div className="detail-item">
                  <label>External Date</label>
                  <span>{fmtDate(br.external_timestamp)}</span>
                </div>
                {br.resolved_at && (
                  <div className="detail-item">
                    <label>Resolved At</label>
                    <span>{fmtDate(br.resolved_at)}</span>
                  </div>
                )}
                <div className="detail-item" style={{ gridColumn: "1/-1" }}>
                  <label>Description</label>
                  <span>{fmt(br.description)}</span>
                </div>

                <div className="detail-item" style={{ gridColumn: "1/-1", marginTop: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <label style={{ margin: 0 }}>✨ AI Resolution Assistant</label>
                    {!aiExplanation && (
                      <button 
                        className="action-btn" 
                        style={{ padding: "4px 10px", fontSize: "0.8rem", background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                        onClick={handleAskAi}
                        disabled={askingAi}
                      >
                        {askingAi ? "Analyzing..." : "Ask AI to Explain"}
                      </button>
                    )}
                  </div>
                  {aiExplanation ? (
                    <div style={{ background: "rgba(59, 130, 246, 0.08)", padding: "12px", borderRadius: "6px", border: "1px solid rgba(59, 130, 246, 0.2)", fontSize: "0.9rem", color: "var(--text-primary)", lineHeight: 1.5 }}>
                      {aiExplanation}
                    </div>
                  ) : (
                    <div style={{ fontSize: "0.85rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                      Click the button above to ask Gemini to analyze this break.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button className="action-btn" onClick={onClose}>Close</button>
          {br && !br.resolved && (
            <button
              className="action-btn success"
              onClick={handleResolve}
              disabled={resolving}
            >
              {resolving ? "Resolving…" : "✓ Mark Resolved"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Reconcile Control ────────────────────────────────────────────────────────
function ReconcileControl({ source, onJobComplete, addToast }) {
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [triggering, setTriggering] = useState(false);
  const [ledgerFile, setLedgerFile] = useState(null);
  const [statementFile, setStatementFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const pollRef = useRef(null);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };

  const pollStatus = useCallback(async (id) => {
    try {
      const status = await getJobStatus(id);
      setJobStatus(status);
      if (status.status === "complete" || status.status === "failed") {
        stopPolling();
        if (status.status === "complete") {
          addToast(
            `Reconciliation complete — ${status.breaks_detected ?? 0} breaks detected`,
            "success"
          );
          onJobComplete();
        } else {
          addToast("Reconciliation job failed", "error");
        }
      }
    } catch {
      /* ignore transient errors */
    }
  }, [onJobComplete, addToast]);

  const handleRun = async () => {
    setTriggering(true);
    try {
      const res = await triggerReconciliation(source);
      setJobId(res.job_id);
      setJobStatus({ status: "pending" });
      addToast("Reconciliation job queued", "success");
      // Poll every 2 seconds
      pollRef.current = setInterval(() => pollStatus(res.job_id), 2000);
    } catch (e) {
      addToast("Failed to start reconciliation", "error");
    } finally {
      setTriggering(false);
    }
  };
  
  const handleUpload = async () => {
    if (!ledgerFile || !statementFile) {
      addToast("Please select both files", "error");
      return;
    }
    setUploading(true);
    try {
      await uploadLedger(ledgerFile);
      await uploadStatement(statementFile);
      addToast("Files uploaded successfully", "success");
    } catch (err) {
      addToast(err.message || "Failed to upload files", "error");
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => () => stopPolling(), []);

  const statusLabel = jobStatus
    ? { pending: "Queued", running: "Running…", complete: "Complete", failed: "Failed" }[
        jobStatus.status
      ] ?? jobStatus.status
    : null;

  return (
    <div className="reconcile-card">
      <div className="reconcile-info">
        <h3>Reconciliation Engine</h3>
        <p>
          Compare the internal ledger against the external bank statement.
          Runs as an async background job — the API returns immediately.
        </p>
        {source === "synthetic" && (
          <div style={{ marginTop: 12, padding: 12, backgroundColor: "rgba(59, 130, 246, 0.1)", borderLeft: "4px solid #3b82f6", borderRadius: 4, fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            <strong>Note to Viewers:</strong> The data shown in the "Synthetic Dataset" mode is entirely fictional. It was procedurally generated by a Python script (<code>backend/data/generate_data.py</code>) to simulate 5,000+ realistic financial transactions, including deliberately planted edge cases like currency exchange (FX) rounding errors, timing lags, and missing rows. This allows us to rigorously evaluate the engine's accuracy safely.
          </div>
        )}
      </div>
      
      {source === "uploaded" && (
        <div style={{ marginBottom: 20, display: "flex", gap: 20, flexWrap: "wrap", background: "var(--bg-secondary)", padding: 16, borderRadius: 8, border: "1px solid var(--border)" }}>
          <div>
            <label style={{display: "block", marginBottom: 8, fontSize: "0.9rem", fontWeight: 600}}>Internal Ledger CSV</label>
            <input type="file" accept=".csv" onChange={(e) => setLedgerFile(e.target.files[0])} />
          </div>
          <div>
            <label style={{display: "block", marginBottom: 8, fontSize: "0.9rem", fontWeight: 600}}>External Statement CSV</label>
            <input type="file" accept=".csv" onChange={(e) => setStatementFile(e.target.files[0])} />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button className="action-btn" onClick={handleUpload} disabled={uploading}>
              {uploading ? "Uploading..." : "Upload Files"}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        {jobStatus && (
          <div className="job-status">
            <div className={`status-dot ${jobStatus.status}`} />
            <span>
              {statusLabel}
              {jobStatus.breaks_detected !== undefined &&
                jobStatus.breaks_detected !== null &&
                ` — ${jobStatus.breaks_detected} breaks`}
            </span>
          </div>
        )}
        <button
          className="action-btn primary"
          onClick={handleRun}
          disabled={triggering || jobStatus?.status === "running"}
          id="btn-run-reconciliation"
        >
          {triggering ? "Queuing…" : "▶ Run Reconciliation"}
        </button>
      </div>
    </div>
  );
}

// ─── Stats Cards ──────────────────────────────────────────────────────────────
function StatsCards({ stats, source }) {
  if (source === "uploaded") {
    return (
      <div className="stats-grid" style={{ gridTemplateColumns: "1fr" }}>
        <div className="stat-card" style={{ "--accent-color": "#64748b", textAlign: "center", padding: "30px 20px" }}>
          <div style={{ fontSize: "1.2rem", fontWeight: 600, color: "var(--text-secondary)" }}>
            Unevaluated — no ground truth available for uploaded data.
          </div>
          <div style={{ fontSize: "0.95rem", color: "var(--text-muted)", marginTop: 8 }}>
            Precision and recall metrics are only available for the evaluated synthetic dataset.
          </div>
        </div>
      </div>
    );
  }

  if (!stats) return null;
  const rate = stats.resolution_rate_pct ?? 0;
  return (
    <div className="stats-grid">
      <div className="stat-card" style={{ "--accent-color": "#3b82f6" }}>
        <div className="stat-value">{stats.total_transactions_in_ledger?.toLocaleString() ?? "—"}</div>
        <div className="stat-label">Total Ledger Txns</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#ef4444" }}>
        <div className="stat-value">{stats.total_breaks_detected?.toLocaleString() ?? "—"}</div>
        <div className="stat-label">Breaks Detected</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#10b981" }}>
        <div className="stat-value">{stats.total_breaks_resolved?.toLocaleString() ?? "—"}</div>
        <div className="stat-label">Breaks Resolved</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#8b5cf6" }}>
        <div className="stat-value">{rate.toFixed(1)}%</div>
        <div className="stat-label">Resolution Rate</div>
        <div className="progress-bar" style={{ marginTop: 10 }}>
          <div className="progress-fill" style={{ width: `${Math.min(rate, 100)}%`, background: "linear-gradient(90deg,#8b5cf6,#6d28d9)" }} />
        </div>
      </div>
    </div>
  );
}

// ─── Breaks Chart ─────────────────────────────────────────────────────────────
function BreaksChart({ stats }) {
  if (!stats?.breaks_by_type?.length) return null;
  const data = stats.breaks_by_type.map((b) => ({
    name: b.break_type.replace(/_/g, " "),
    raw: b.break_type,
    count: b.count,
    resolved: b.resolved_count,
    unresolved: b.count - b.resolved_count,
  }));

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
      <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 8, padding: "12px 16px" }}>
        <div style={{ fontWeight: 700, marginBottom: 6, color: "var(--text-primary)" }}>{label}</div>
        {payload.map((p) => (
          <div key={p.name} style={{ color: p.fill, fontSize: "0.85rem" }}>
            {p.name}: {p.value}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="chart-card">
      <div className="chart-title">Breaks by Type</div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} barCategoryGap="30%">
          <XAxis
            dataKey="name"
            tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="unresolved" name="Unresolved" radius={[4, 4, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.raw} fill={BREAK_COLORS[entry.raw] ?? "#64748b"} opacity={0.85} />
            ))}
          </Bar>
          <Bar dataKey="resolved" name="Resolved" radius={[4, 4, 0, 0]} fill="rgba(255,255,255,0.12)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Breaks Table ─────────────────────────────────────────────────────────────
function BreaksTable({ source, onSelectBreak, refreshSignal }) {
  const [breaks, setBreaks] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [resolvedFilter, setResolvedFilter] = useState("");
  const [sortField, setSortField] = useState("detected_at");
  const [sortDir, setSortDir] = useState("desc");
  const PAGE_SIZE = 25;

  const fetchBreaks = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, page_size: PAGE_SIZE, source };
      if (typeFilter !== "ALL") params.break_type = typeFilter;
      if (resolvedFilter !== "") params.resolved = resolvedFilter;
      const data = await getBreaks(params);
      setBreaks(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (e) {
      setBreaks([]);
    } finally {
      setLoading(false);
    }
  }, [page, typeFilter, resolvedFilter, source]);

  const handleExport = async () => {
    try {
      const params = { source };
      if (typeFilter !== "ALL") params.break_type = typeFilter;
      if (resolvedFilter !== "") params.resolved = resolvedFilter;
      
      const blob = await exportBreaks(params);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      a.download = `reconciliation_breaks_${new Date().getTime()}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert("Export failed. Please try again.");
    }
  };

  useEffect(() => { fetchBreaks(); }, [fetchBreaks, refreshSignal]);
  useEffect(() => { setPage(1); }, [typeFilter, resolvedFilter, source]);

  const handleSort = (field) => {
    if (sortField === field) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortField(field); setSortDir("asc"); }
  };

  // Client-side sort (API doesn't support server-side sort in this build)
  const sorted = [...breaks].sort((a, b) => {
    let av = a[sortField], bv = b[sortField];
    if (typeof av === "string") av = av.toLowerCase();
    if (typeof bv === "string") bv = bv.toLowerCase();
    if (av < bv) return sortDir === "asc" ? -1 : 1;
    if (av > bv) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const sortIcon = (f) => (
    <span className="sort-icon">{sortField === f ? (sortDir === "asc" ? "↑" : "↓") : "↕"}</span>
  );

  const fmtAmt = (v) => (v !== null && v !== undefined ? `$${parseFloat(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}` : "—");
  const fmtDate = (v) => v ? new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="table-wrap">
      <div className="table-header">
        <span className="table-title">Reconciliation Breaks <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.85rem" }}>({total.toLocaleString()} total)</span></span>
        <div className="table-filters">
          <select
            className="filter-select"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            id="filter-break-type"
          >
            {BREAK_TYPE_OPTIONS.map((o) => (
              <option key={o} value={o}>{o === "ALL" ? "All Types" : o.replace(/_/g, " ")}</option>
            ))}
          </select>
          <select
            className="filter-select"
            value={resolvedFilter}
            onChange={(e) => setResolvedFilter(e.target.value)}
            id="filter-resolved"
          >
            <option value="">All Status</option>
            <option value="false">Unresolved</option>
            <option value="true">Resolved</option>
          </select>
          <button 
            className="action-btn" 
            onClick={handleExport}
            style={{ marginLeft: 8 }}
            title="Download CSV"
          >
            📥 Export CSV
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading-wrap"><div className="spinner" /><span>Loading breaks…</span></div>
      ) : sorted.length === 0 ? (
        <div className="empty-state">
          <div className="icon">📊</div>
          <h3>No breaks found</h3>
          <p>Run a reconciliation job to detect discrepancies.</p>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th onClick={() => handleSort("transaction_id")} className={sortField === "transaction_id" ? "sorted" : ""}>
                  Transaction ID {sortIcon("transaction_id")}
                </th>
                <th onClick={() => handleSort("break_type")} className={sortField === "break_type" ? "sorted" : ""}>
                  Break Type {sortIcon("break_type")}
                </th>
                <th onClick={() => handleSort("internal_amount")} className={sortField === "internal_amount" ? "sorted" : ""}>
                  Internal Amt {sortIcon("internal_amount")}
                </th>
                <th onClick={() => handleSort("external_amount")} className={sortField === "external_amount" ? "sorted" : ""}>
                  External Amt {sortIcon("external_amount")}
                </th>
                <th onClick={() => handleSort("delta_amount")} className={sortField === "delta_amount" ? "sorted" : ""}>
                  Delta {sortIcon("delta_amount")}
                </th>
                <th onClick={() => handleSort("detected_at")} className={sortField === "detected_at" ? "sorted" : ""}>
                  Detected {sortIcon("detected_at")}
                </th>
                <th onClick={() => handleSort("resolved")} className={sortField === "resolved" ? "sorted" : ""}>
                  Status {sortIcon("resolved")}
                </th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((br) => {
                const delta = br.delta_amount !== null ? parseFloat(br.delta_amount) : null;
                return (
                  <tr key={br.break_id}>
                    <td><span className="txn-id">{br.transaction_id}</span></td>
                    <td><BreakTypeBadge type={br.break_type} /></td>
                    <td><span className="amount">{fmtAmt(br.internal_amount)}</span></td>
                    <td><span className="amount">{fmtAmt(br.external_amount)}</span></td>
                    <td>
                      {delta !== null ? (
                        <span className={`amount ${delta > 0 ? "amount-positive" : delta < 0 ? "amount-negative" : ""}`}>
                          {delta >= 0 ? "+" : ""}{delta.toFixed(4)}
                        </span>
                      ) : "—"}
                    </td>
                    <td>{fmtDate(br.detected_at)}</td>
                    <td>
                      <span className={`badge badge-${br.resolved ? "resolved" : "unresolved"}`}>
                        {br.resolved ? "Resolved" : "Open"}
                      </span>
                    </td>
                    <td>
                      <button
                        className="action-btn"
                        onClick={() => onSelectBreak(br.break_id)}
                        id={`btn-view-break-${br.break_id}`}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          <span className="pagination-info">
            Page {page} of {totalPages} — {total.toLocaleString()} breaks
          </span>
          <div className="pagination-btns">
            <button className="action-btn" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              ← Prev
            </button>
            <button className="action-btn" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [source, setSource] = useState("synthetic");
  const [stats, setStats] = useState(null);
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [selectedBreakId, setSelectedBreakId] = useState(null);
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = "success") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const data = await getStats(source);
      setStats(data);
    } catch {
      /* stats may not be available before first reconciliation run */
    }
  }, [source]);

  useEffect(() => { loadStats(); }, [loadStats, refreshSignal]);

  const handleJobComplete = useCallback(() => {
    setRefreshSignal((s) => s + 1);
  }, []);

  const handleResolved = useCallback(() => {
    setRefreshSignal((s) => s + 1);
  }, []);

  return (
    <div className="app">
      {/* ── Navbar ── */}
      <nav className="navbar">
        <div className="navbar-brand">
          <div className="logo-icon">⚖</div>
          <span>Ledger Recon</span>
        </div>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Reconciliation Engine v1.0
        </div>
      </nav>

      <main>
        {/* ── Page title ── */}
        <div style={{ marginBottom: 28, display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: 6 }}>
              Reconciliation Dashboard
            </h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
              Detect and resolve discrepancies between your internal ledger and external bank statements.
            </p>
          </div>
          
          <div style={{ display: "flex", background: "var(--bg-secondary)", borderRadius: 8, padding: 4, border: "1px solid var(--border)" }}>
            <button 
              className={`action-btn ${source === "synthetic" ? "primary" : ""}`} 
              style={{ border: "none", background: source === "synthetic" ? "var(--bg-card)" : "transparent", color: source === "synthetic" ? "var(--text-primary)" : "var(--text-secondary)" }}
              onClick={() => { setSource("synthetic"); setStats(null); }}
            >
              Synthetic Dataset
            </button>
            <button 
              className={`action-btn ${source === "uploaded" ? "primary" : ""}`} 
              style={{ border: "none", background: source === "uploaded" ? "var(--bg-card)" : "transparent", color: source === "uploaded" ? "var(--text-primary)" : "var(--text-secondary)" }}
              onClick={() => { setSource("uploaded"); setStats(null); }}
            >
              Uploaded Data
            </button>
          </div>
        </div>

        {/* ── Reconcile Control ── */}
        <ReconcileControl source={source} onJobComplete={handleJobComplete} addToast={addToast} />

        {/* ── Stats Cards ── */}
        <StatsCards stats={stats} source={source} />

        {/* ── Chart ── */}
        {source !== "uploaded" && stats?.breaks_by_type?.length > 0 && <BreaksChart stats={stats} />}

        {/* ── Breaks Table ── */}
        <BreaksTable
          source={source}
          onSelectBreak={setSelectedBreakId}
          refreshSignal={refreshSignal}
        />
      </main>

      {/* ── Break Detail Modal ── */}
      {selectedBreakId && (
        <BreakDetailModal
          breakId={selectedBreakId}
          onClose={() => setSelectedBreakId(null)}
          onResolved={handleResolved}
          addToast={addToast}
        />
      )}

      {/* ── Toasts ── */}
      <Toast toasts={toasts} />
    </div>
  );
}
