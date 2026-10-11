// Browser-only adapter for precomputed sample results. It never runs the matcher.
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
  "source",
  "evidence_side",
  "occurrence",
];
const AMOUNT_FIELDS = new Set([
  "internal_amount",
  "external_amount",
  "delta_amount",
]);

function scaled(value) {
  const text = String(value);
  const [whole, fraction = ""] = text.replace(/^-/, "").split(".");
  return (
    (BigInt(whole) * 10000n + BigInt(fraction.padEnd(4, "0"))) *
    (text.startsWith("-") ? -1n : 1n)
  );
}

function csvCell(value, protectFormula = true) {
  let text = value == null ? "" : String(value);
  if (protectFormula && typeof value === "string" && /^[\s]*[=+\-@]/.test(text))
    text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}

export function createDemoClient(snapshot, storage) {
  const key = `ledger-recon.demo.${snapshot.input_fingerprint}`;
  let state = { resolutions: {}, jobs: [] };
  try {
    const saved = JSON.parse(storage?.getItem(key) || "null");
    if (
      saved &&
      typeof saved.resolutions === "object" &&
      saved.resolutions &&
      Array.isArray(saved.jobs)
    )
      state = saved;
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
    }));
  }
  function filtered(params) {
    if (params.get("source") === "uploaded") return [];
    return records().filter(
      (item) =>
        (!params.get("break_type") ||
          item.break_type === params.get("break_type")) &&
        (!params.has("resolved") ||
          item.resolved === (params.get("resolved") === "true")),
    );
  }
  return {
    reset() {
      state = { resolutions: {}, jobs: [] };
      save();
    },
    async request(path, options = {}) {
      if (options.signal?.aborted)
        throw new DOMException("Aborted", "AbortError");
      const { pathname, searchParams: params } = new URL(
        path,
        "https://demo.invalid",
      );
      if (pathname === "/stats") {
        const items = filtered(params);
        const resolved = items.filter((item) => item.resolved).length;
        const byType = new Map();
        for (const item of items) {
          const group = byType.get(item.break_type) || {
            break_type: item.break_type,
            count: 0,
            resolved_count: 0,
          };
          group.count++;
          if (item.resolved) group.resolved_count++;
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
          resolution_rate_pct: items.length
            ? Math.round((resolved / items.length) * 10000) / 100
            : 0,
          breaks_by_type: [...byType.values()].sort((a, b) =>
            a.break_type.localeCompare(b.break_type),
          ),
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
      if (pathname === "/breaks") {
        const field = params.get("sort_by") || "detected_at";
        const direction = params.get("sort_dir") === "asc" ? 1 : -1;
        const items = filtered(params).sort((a, b) => {
          let av = a[field],
            bv = b[field];
          if (av == null || bv == null)
            return av == null && bv == null
              ? a.break_id.localeCompare(b.break_id)
              : av == null
                ? 1
                : -1;
          if (AMOUNT_FIELDS.has(field)) {
            av = scaled(av);
            bv = scaled(bv);
          }
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
        if (action === "resolve") {
          state.resolutions[id] ||= new Date().toISOString();
          save();
          return {
            break_id: id,
            resolved: true,
            resolved_at: state.resolutions[id],
            message: "Resolved in your browser demo",
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
