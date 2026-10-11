const env = import.meta.env;
const API_BASE = (env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export const DEMO_MODE =
  env.VITE_DEMO_MODE === "true" ||
  (env.VITE_DEMO_MODE !== "false" && env.PROD && !API_BASE);

async function demo() {
  const { client } = await import("./demo/index.js");
  return client;
}

async function request(path, options = {}, blob = false) {
  if (DEMO_MODE) return (await demo()).request(path, options);
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: options.headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((error) => error.msg).join("; ")
      : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return blob ? response.blob() : response.json();
}

const query = (params) =>
  new URLSearchParams(
    Object.entries(params).filter(
      ([, value]) =>
        value !== undefined &&
        value !== null &&
        value !== "" &&
        value !== "ALL",
    ),
  ).toString();

export const triggerReconciliation = (source) =>
  request(`/reconcile/run?${query({ source })}`, { method: "POST" });
export const getJobStatus = (id, signal) =>
  request(`/reconcile/status/${id}`, { signal });
export const getJobs = (source, signal) =>
  request(`/reconcile/jobs?${query({ source })}`, { signal });
export const getBreaks = (params, signal) =>
  request(`/breaks?${query(params)}`, { signal });
export const getStats = (source, signal) =>
  request(`/stats?${query({ source })}`, { signal });
export const getBreak = (id, signal) => request(`/breaks/${id}`, { signal });
export const resolveBreak = (id) =>
  request(`/breaks/${id}/resolve`, { method: "POST" });
export const explainBreakWithAI = (id) =>
  request(`/breaks/${id}/ai-explain`, { method: "POST" });
export const exportBreaks = (params) =>
  request(`/breaks/export?${query(params)}`, {}, true);
export const uploadPair = (ledger, statement) => {
  const body = new FormData();
  body.append("ledger", ledger);
  body.append("statement", statement);
  return request("/reconcile/upload", { method: "POST", body });
};
export const resetDemo = async () => (await demo()).reset();
