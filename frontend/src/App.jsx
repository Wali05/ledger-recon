import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  Play, Upload, Download, Sparkles, Check, X, ChevronLeft, ChevronRight,
  Scale, FileText, Layers, Activity, TriangleAlert, CircleCheck, Percent,
  FileSearch, Landmark,
} from "lucide-react";
import {
  triggerReconciliation, getJobStatus, getBreaks, getStats, resolveBreak, getBreak,
  uploadLedger, uploadStatement, explainBreakWithAI, exportBreaks
} from "./api";
import "./index.css";

// ─── Constants ────────────────────────────────────────────────────────────────
const BREAK_COLORS = {
  AMOUNT_MISMATCH: "#b97d18",
  MISSING_INTERNAL: "#c0442e",
  MISSING_EXTERNAL: "#d97757",
  DUPLICATE: "#8560ad",
  TIMING_LAG: "#2596a3",
  FX_ROUNDING: "#3d8a5f",
  UNKNOWN: "#9a9384",
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
          <span className="toast-icon">
            {t.type === "success" ? <Check size={14} strokeWidth={3} /> : <X size={14} strokeWidth={3} />}
          </span>
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
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="modal-body">
          {!br ? (
            <div className="loading-wrap"><div className="spinner" /></div>
          ) : (
            <>
              <div style={{ marginBottom: 20, display: "flex", gap: 8, alignItems: "center" }}>
                <BreakTypeBadge type={br.break_type} />
                {br.resolved && <span className="badge badge-resolved">Resolved</span>}
              </div>
              <div className="detail-grid">
                <div className="detail-item">
                  <label>Transaction ID</label>
                  <span className="mono">{br.transaction_id}</span>
                </div>
                <div className="detail-item">
                  <label>Break ID</label>
                  <span className="mono">{br.break_id}</span>
                </div>
                <div className="detail-item">
                  <label>Internal Amount</label>
                  <span className="amount">{fmtAmt(br.internal_amount)}</span>
                </div>
                <div className="detail-item">
                  <label>External Amount</label>
                  <span className="amount">{fmtAmt(br.external_amount)}</span>
                </div>
                <div className="detail-item">
                  <label>Delta</label>
                  <span
                    className={`amount ${
                      parseFloat(br.delta_amount) > 0
                        ? "amount-positive"
                        : parseFloat(br.delta_amount) < 0
                        ? "amount-negative"
                        : ""
                    }`}
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
                <div className="detail-item span-2">
                  <label>Description</label>
                  <span>{fmt(br.description)}</span>
                </div>

                <div className="ai-panel">
                  <div className="ai-panel-head">
                    <label><Sparkles size={14} /> AI Resolution Assistant</label>
                    {!aiExplanation && (
                      <button
                        className="action-btn"
                        style={{ padding: "5px 12px", fontSize: "0.8rem" }}
                        onClick={handleAskAi}
                        disabled={askingAi}
                      >
                        {askingAi ? "Analyzing…" : "Ask AI to Explain"}
                      </button>
                    )}
                  </div>
                  {aiExplanation ? (
                    <div className="ai-answer">{aiExplanation}</div>
                  ) : (
                    <div className="ai-hint">
                      Click the button above to ask Gemini to analyze this break.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button className="action-btn ghost" onClick={onClose}>Close</button>
          {br && !br.resolved && (
            <button
              className="action-btn success"
              onClick={handleResolve}
              disabled={resolving}
            >
              <Check size={15} strokeWidth={2.5} />
              {resolving ? "Resolving…" : "Mark Resolved"}
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
          <div className="note-callout">
            <strong>Note to Viewers:</strong> The data shown in the "Synthetic Dataset" mode is entirely fictional. It was procedurally generated by a Python script (<code>backend/data/generate_data.py</code>) to simulate 5,000+ realistic financial transactions, including deliberately planted edge cases like currency exchange (FX) rounding errors, timing lags, and missing rows. This allows us to rigorously evaluate the engine's accuracy safely.
          </div>
        )}
      </div>

      {source === "uploaded" && (
        <div className="upload-panel">
          <div className="upload-field">
            <label><FileText size={15} /> Internal Ledger CSV</label>
            <input type="file" accept=".csv" onChange={(e) => setLedgerFile(e.target.files[0])} />
          </div>
          <div className="upload-field">
            <label><Landmark size={15} /> External Statement CSV</label>
            <input type="file" accept=".csv" onChange={(e) => setStatementFile(e.target.files[0])} />
          </div>
          <button className="action-btn" onClick={handleUpload} disabled={uploading}>
            <Upload size={15} />
            {uploading ? "Uploading…" : "Upload Files"}
          </button>
        </div>
      )}

      <div className="run-row">
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
          <Play size={15} strokeWidth={2.5} />
          {triggering ? "Queuing…" : "Run Reconciliation"}
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
        <div className="stat-card stat-empty" style={{ "--accent-color": "#9a9384" }}>
          <div className="stat-empty-title">
            Unevaluated — no ground truth available for uploaded data.
          </div>
          <div className="stat-empty-sub">
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
      <div className="stat-card" style={{ "--accent-color": "#4f6db8" }}>
        <div className="stat-head">
          <div className="stat-value">{stats.total_transactions_in_ledger?.toLocaleString() ?? "—"}</div>
          <div className="stat-icon"><Layers size={19} /></div>
        </div>
        <div className="stat-label">Total Ledger Txns</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#c0442e" }}>
        <div className="stat-head">
          <div className="stat-value">{stats.total_breaks_detected?.toLocaleString() ?? "—"}</div>
          <div className="stat-icon"><TriangleAlert size={19} /></div>
        </div>
        <div className="stat-label">Breaks Detected</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#3d8a5f" }}>
        <div className="stat-head">
          <div className="stat-value">{stats.total_breaks_resolved?.toLocaleString() ?? "—"}</div>
          <div className="stat-icon"><CircleCheck size={19} /></div>
        </div>
        <div className="stat-label">Breaks Resolved</div>
      </div>
      <div className="stat-card" style={{ "--accent-color": "#8560ad" }}>
        <div className="stat-head">
          <div className="stat-value">{rate.toFixed(1)}%</div>
          <div className="stat-icon"><Percent size={19} /></div>
        </div>
        <div className="stat-label">Resolution Rate</div>
        <div className="progress-bar" style={{ marginTop: 12 }}>
          <div
            className="progress-fill"
            style={{ width: `${Math.min(rate, 100)}%`, background: "linear-gradient(90deg,#8560ad,#6d4c93)" }}
          />
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
      <div className="chart-tooltip">
        <div className="tt-label">{label}</div>
        {payload.map((p) => (
          <div key={p.name} className="tt-row" style={{ color: p.fill }}>
            {p.name}: {p.value}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="chart-card">
      <div className="chart-title">Breaks by Type</div>
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={data} barCategoryGap="30%">
          <XAxis
            dataKey="name"
            tick={{ fill: "#6b6557", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#6b6557", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(217, 119, 87, 0.07)" }} />
          <Bar dataKey="unresolved" name="Unresolved" radius={[6, 6, 0, 0]}>
            {data.map((entry) => (
              <Cell key={entry.raw} fill={BREAK_COLORS[entry.raw] ?? "#9a9384"} opacity={0.9} />
            ))}
          </Bar>
          <Bar dataKey="resolved" name="Resolved" radius={[6, 6, 0, 0]} fill="rgba(41, 37, 30, 0.14)" />
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
        <span className="table-title">
          Reconciliation Breaks
          <span className="table-count">({total.toLocaleString()} total)</span>
        </span>
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
            title="Download CSV"
          >
            <Download size={15} />
            Export CSV
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading-wrap"><div className="spinner" /><span>Loading breaks…</span></div>
      ) : sorted.length === 0 ? (
        <div className="empty-state">
          <div className="icon"><FileSearch size={26} /></div>
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
                        style={{ padding: "6px 13px", fontSize: "0.8rem" }}
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
              <ChevronLeft size={15} /> Prev
            </button>
            <button className="action-btn" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              Next <ChevronRight size={15} />
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
          <div className="logo-icon"><Scale size={19} /></div>
          <span>Ledger Recon</span>
        </div>
        <div className="navbar-meta">
          <div className="live-dot" />
          <span>Reconciliation Engine v1.0</span>
        </div>
      </nav>

      <main>
        {/* ── Page title ── */}
        <div className="page-head">
          <div>
            <h1 className="page-title">
              Reconciliation <em>Dashboard</em>
            </h1>
            <p className="page-sub">
              Detect and resolve discrepancies between your internal ledger and external bank statements.
            </p>
          </div>

          <div className="seg-toggle">
            <button
              className={`seg-btn ${source === "synthetic" ? "active" : ""}`}
              onClick={() => { setSource("synthetic"); setStats(null); }}
            >
              Synthetic Dataset
            </button>
            <button
              className={`seg-btn ${source === "uploaded" ? "active" : ""}`}
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
