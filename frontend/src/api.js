const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status} ${err}`);
  }
  return res.json();
}

// ── Reconciliation ──────────────────────────────────────────────────────────
export const triggerReconciliation = (source = "synthetic") =>
  request(`/reconcile/run?source=${source}`, { method: "POST" });

export const getJobStatus = (jobId) =>
  request(`/reconcile/status/${jobId}`);

export const uploadLedger = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/reconcile/upload/ledger`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload ledger");
  }
  return res.json();
};

export const uploadStatement = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/reconcile/upload/statement`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload statement");
  }
  return res.json();
};

// ── Breaks ──────────────────────────────────────────────────────────────────
export const getBreaks = (params = {}) => {
  const qs = new URLSearchParams();
  if (params.break_type) qs.append("break_type", params.break_type);
  if (params.resolved !== undefined && params.resolved !== "") qs.append("resolved", params.resolved);
  if (params.page) qs.append("page", params.page);
  if (params.page_size) qs.append("page_size", params.page_size);
  if (params.source) qs.append("source", params.source);
  return request(`/breaks?${qs.toString()}`);
};

export const exportBreaks = async (params = {}) => {
  const qs = new URLSearchParams();
  if (params.break_type) qs.append("break_type", params.break_type);
  if (params.resolved !== undefined && params.resolved !== "") qs.append("resolved", params.resolved);
  if (params.source) qs.append("source", params.source);
  
  const res = await fetch(`${API_BASE}/breaks/export?${qs.toString()}`);
  if (!res.ok) {
    throw new Error("Export failed");
  }
  return res.blob();
};

export const getBreak = (breakId) => request(`/breaks/${breakId}`);

export const resolveBreak = (breakId) =>
  request(`/breaks/${breakId}/resolve`, { method: "POST" });

export const explainBreakWithAI = async (breakId) => {
  const res = await fetch(`${API_BASE}/breaks/${breakId}/ai-explain`, { method: "POST" });
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("AI rate limit reached. Please try again later.");
    }
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch AI explanation");
  }
  return res.json();
};

// ── Stats ───────────────────────────────────────────────────────────────────
export const getStats = (source = "synthetic") => request(`/stats?source=${source}`);

