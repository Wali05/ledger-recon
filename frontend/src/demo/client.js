// Browser-only adapter for precomputed sample results. It never runs the matcher.
// It mirrors the API's filters, sorting, review rules and statistics so the
// public demo behaves like the connected app.
import { scaled, unscaled } from "../format.js";

const EXPORT_FIELDS = [
  "break_id",
  "transaction_id",
  "external_transaction_id",
  "break_type",
  "currency",
  "internal_amount",
  "external_amount",
  "delta_amount",
  "internal_timestamp",
  "external_timestamp",
  "description",
  "detected_at",
  "resolved",
  "resolved_at",
  "resolved_by",
  "source",
  "evidence_side",
  "occurrence",
  "confidence",
  "related_rows",
];
const AMOUNT_FIELDS = new Set([
  "internal_amount",
  "external_amount",
  "delta_amount",
]);
const CONFIDENCE_RANK = { low: 0, medium: 1, high: 2 };

function csvCell(value, protectFormula = true) {
  if (Array.isArray(value))
    value = value.map((row) => row.transaction_id).join(" ");
  let text = value == null ? "" : String(value);
  if (protectFormula && typeof value === "string" && /^[\s]*[=+\-@]/.test(text))
    text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}

// Same rule as the API: the difference for amount breaks, otherwise the gross
// amount that has not been confirmed on both sides.
function exposure(item) {
  const absolute = (value) => {
    const amount = scaled(value);
    return amount < 0n ? -amount : amount;
  };
  if (
    ["AMOUNT_MISMATCH", "FX_ROUNDING"].includes(item.break_type) &&
    item.delta_amount != null
  )
    return absolute(item.delta_amount);
  const amount = item.internal_amount ?? item.external_amount;
  return amount == null ? 0n : absolute(amount);
}

function ledgerRowsInBreak(item) {
  if (item.evidence_side === "many_internal")
    return item.related_rows?.length || 0;
  return item.evidence_side === "external" ? 0 : 1;
}

const DEMO_REVIEWER = "demo visitor";

export function createDemoClient(snapshot, storage) {
  const key = `ledger-recon.demo.${snapshot.input_fingerprint}`;
  let state = { resolutions: {}, jobs: [], events: [] };
  try {
    const saved = JSON.parse(storage?.getItem(key) || "null");
    if (
      saved &&
      typeof saved.resolutions === "object" &&
      saved.resolutions &&
      Array.isArray(saved.jobs)
    )
      state = { events: [], ...saved };
  } catch {
    /* Storage may be disabled or contain an older format. */
  }
  function save() {
    try {
      storage?.setItem(key, JSON.stringify(state));
    } catch {
      /* Remain usable in memory. */
    }
  }
  function records() {
    return snapshot.items.map((item) => ({
      ...item,
      resolved: !!state.resolutions[item.break_id],
      resolved_at: state.resolutions[item.break_id] || null,
      resolved_by: state.resolutions[item.break_id] ? DEMO_REVIEWER : null,
    }));
  }
  function filtered(params) {
    if (params.get("source") === "uploaded") return [];
    const search = params.get("q")?.trim().toLowerCase();
    return records().filter(
      (item) =>
        (!params.get("break_type") ||
          item.break_type === params.get("break_type")) &&
        (!params.has("resolved") ||
          item.resolved === (params.get("resolved") === "true")) &&
        (!params.get("confidence") ||
          item.confidence === params.get("confidence")) &&
        (!search ||
          [
            item.transaction_id,
            item.external_transaction_id,
            item.description,
          ].some((text) => text?.toLowerCase().includes(search))),
    );
  }
  function review(id, resolve, note) {
    const item = records().find((item) => item.break_id === id);
    if (!item || resolve === item.resolved) return false;
    const now = new Date().toISOString();
    if (resolve) state.resolutions[id] = now;
    else delete state.resolutions[id];
    state.events.push({
      event_id: crypto.randomUUID(),
      break_id: id,
      source: "synthetic",
      transaction_id: item.transaction_id,
      break_type: item.break_type,
      action: resolve ? "resolved" : "reopened",
      reviewer: DEMO_REVIEWER,
      note: note?.trim() || null,
      created_at: now,
    });
    return true;
  }
  function body(options) {
    try {
      return JSON.parse(options.body || "{}");
    } catch {
      return {};
    }
  }
  return {
    reset() {
      state = { resolutions: {}, jobs: [], events: [] };
      save();
    },
    async request(path, options = {}) {
      if (options.signal?.aborted)
        throw new DOMException("Aborted", "AbortError");
      const { pathname, searchParams: params } = new URL(
        path,
        "https://demo.invalid",
      );
      if (pathname === "/session")
        return { auth_required: false, reviewer: DEMO_REVIEWER };
      if (pathname === "/stats") {
        const items = filtered(params);
        const resolved = items.filter((item) => item.resolved).length;
        const byType = new Map();
        const byConfidence = new Map();
        let openValue = 0n;
        for (const item of items) {
          const group = byType.get(item.break_type) || {
            break_type: item.break_type,
            count: 0,
            resolved_count: 0,
            open: 0n,
          };
          group.count++;
          if (item.resolved) group.resolved_count++;
          else {
            const value = exposure(item);
            group.open += value;
            openValue += value;
            const level = item.confidence || "unrated";
            byConfidence.set(level, (byConfidence.get(level) || 0) + 1);
          }
          byType.set(item.break_type, group);
        }
        const uploaded = params.get("source") === "uploaded";
        return {
          total_transactions_in_ledger: uploaded ? 0 : snapshot.ledger_rows,
          total_transactions_in_statement: uploaded
            ? 0
            : snapshot.statement_rows,
          total_breaks_detected: items.length,
          total_breaks_resolved: resolved,
          ledger_rows_in_breaks: items.reduce(
            (sum, item) => sum + ledgerRowsInBreak(item),
            0,
          ),
          resolution_rate_pct: items.length
            ? Math.round((resolved / items.length) * 10000) / 100
            : 0,
          breaks_by_type: [...byType.values()]
            .sort((a, b) => a.break_type.localeCompare(b.break_type))
            .map(({ open, ...group }) => ({
              ...group,
              open_value: unscaled(open),
            })),
          open_value: unscaled(openValue),
          open_by_confidence: ["low", "medium", "high", "unrated"]
            .filter((level) => byConfidence.has(level))
            .map((level) => ({
              confidence: level,
              open_count: byConfidence.get(level),
            })),
          ai_enabled: false,
        };
      }
      if (pathname === "/reconcile/run") {
        if (params.get("source") === "uploaded")
          throw new Error("Uploads require a connected API");
        const now = new Date().toISOString();
        const job = {
          job_id: crypto.randomUUID(),
          source: "synthetic",
          status: "complete",
          started_at: now,
          finished_at: now,
          transactions_processed: snapshot.ledger_rows,
          breaks_detected: snapshot.items.length,
          breaks_inserted: 0,
          breaks_retired: 0,
          error_message: null,
        };
        state.jobs = [job, ...state.jobs].slice(0, 10);
        save();
        return {
          job_id: job.job_id,
          status: "complete",
          message: "Precomputed sample results loaded",
        };
      }
      if (pathname === "/reconcile/jobs")
        return params.get("source") === "uploaded"
          ? []
          : structuredClone(state.jobs);
      if (pathname.startsWith("/reconcile/status/")) {
        const job = state.jobs.find(
          (job) => job.job_id === pathname.split("/").at(-1),
        );
        if (!job) throw new Error("Demo job not found");
        return structuredClone(job);
      }
      if (pathname === "/breaks/export") {
        const items = filtered(params);
        const lines = [
          EXPORT_FIELDS.join(","),
          ...items.map((item) =>
            EXPORT_FIELDS.map((field) =>
              csvCell(item[field], !AMOUNT_FIELDS.has(field)),
            ).join(","),
          ),
        ];
        return new Blob([lines.join("\r\n") + "\r\n"], { type: "text/csv" });
      }
      if (pathname === "/breaks/bulk-review") {
        const { action, break_ids: ids = [], note } = body(options);
        if (!["resolve", "reopen"].includes(action) || !ids.length)
          throw new Error("Choose at least one break");
        const unique = [...new Set(ids)];
        const changed = unique.filter((id) =>
          review(id, action === "resolve", note),
        ).length;
        save();
        const verb = action === "resolve" ? "resolved" : "reopened";
        return {
          changed,
          unchanged: unique.length - changed,
          message: `${changed} break${changed === 1 ? "" : "s"} ${verb}`,
        };
      }
      if (pathname === "/breaks") {
        const field = params.get("sort_by") || "detected_at";
        const direction = params.get("sort_dir") === "asc" ? 1 : -1;
        const value = (item) =>
          field === "confidence"
            ? (CONFIDENCE_RANK[item.confidence] ?? 3)
            : AMOUNT_FIELDS.has(field) && item[field] != null
              ? scaled(item[field])
              : item[field];
        const items = filtered(params).sort((a, b) => {
          const av = value(a),
            bv = value(b);
          if (av == null || bv == null)
            return av == null && bv == null
              ? a.break_id.localeCompare(b.break_id)
              : av == null
                ? 1
                : -1;
          return av < bv
            ? -direction
            : av > bv
              ? direction
              : a.break_id.localeCompare(b.break_id);
        });
        const page = Number(params.get("page") || 1),
          size = Number(params.get("page_size") || 50);
        return {
          total: items.length,
          page,
          page_size: size,
          items: items.slice((page - 1) * size, page * size),
        };
      }
      if (pathname.startsWith("/breaks/")) {
        const [, , id, action] = pathname.split("/");
        const item = records().find((item) => item.break_id === id);
        if (!item) throw new Error("Demo break not found");
        if (action === "events")
          return structuredClone(
            state.events.filter((event) => event.break_id === id),
          );
        if (action === "resolve" || action === "reopen") {
          const resolve = action === "resolve";
          const changed = review(id, resolve, body(options).note);
          if (changed) save();
          const verb = resolve ? "resolved" : "reopened";
          return {
            break_id: id,
            resolved: resolve,
            resolved_at: state.resolutions[id] || null,
            resolved_by: resolve ? DEMO_REVIEWER : null,
            message: changed
              ? `Break ${verb} in your browser demo`
              : `Break was already ${verb}`,
          };
        }
        if (action === "ai-explain")
          throw new Error("AI explanations are disabled in the demo");
        return item;
      }
      throw new Error("This action requires a connected backend");
    },
  };
}
