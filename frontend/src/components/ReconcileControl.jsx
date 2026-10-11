import { useCallback, useEffect, useState } from "react";
import { FileText, Landmark, Play, Upload } from "lucide-react";
import {
  DEMO_MODE,
  getJobs,
  getJobStatus,
  triggerReconciliation,
  uploadPair,
} from "../api";

export default function ReconcileControl({
  source,
  stats,
  onChange,
  addToast,
}) {
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState("");
  const [files, setFiles] = useState({ ledger: null, statement: null });
  const [dirty, setDirty] = useState(false);
  const [monitorError, setMonitorError] = useState("");

  const restoreJob = useCallback(
    async (signal) => {
      const jobs = await getJobs(source, signal);
      const latest =
        jobs.find((item) => ["pending", "running"].includes(item.status)) ||
        jobs[0];
      if (latest) {
        setJob(latest);
        setJobId(
          ["pending", "running"].includes(latest.status) ? latest.job_id : null,
        );
      }
      setMonitorError("");
    },
    [source],
  );
  useEffect(() => {
    const controller = new AbortController();
    restoreJob(controller.signal).catch((error) => {
      if (error.name !== "AbortError") setMonitorError(error.message);
    });
    return () => controller.abort();
  }, [restoreJob]);

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer,
      failures = 0;
    const deadline = Date.now() + 5 * 60 * 1000;
    async function poll() {
      try {
        const status = await getJobStatus(jobId, controller.signal);
        if (controller.signal.aborted) return;
        failures = 0;
        setJob(status);
        if (["complete", "failed"].includes(status.status)) {
          setJobId(null);
          if (status.status === "complete") {
            addToast(
              DEMO_MODE
                ? "Precomputed sample results loaded"
                : `Complete · ${status.breaks_detected} breaks, ${status.breaks_inserted} new`,
            );
            onChange();
          } else
            addToast(status.error_message || "Reconciliation failed", "error");
          return;
        }
      } catch {
        if (controller.signal.aborted) return;
        if (++failures >= 3) {
          setMonitorError(
            "Status could not be loaded. The job may still be running.",
          );
          setJobId(null);
          return;
        }
      }
      if (Date.now() > deadline) {
        setMonitorError(
          "This job is taking longer than expected. Check its status again.",
        );
        setJobId(null);
        return;
      }
      timer = setTimeout(poll, 1500);
    }
    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, onChange, addToast]);

  async function run() {
    setBusy("run");
    try {
      const response = await triggerReconciliation(source);
      setJob({ status: "pending" });
      setJobId(response.job_id);
      setMonitorError("");
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setBusy("");
    }
  }
  async function upload() {
    setBusy("upload");
    try {
      const result = await uploadPair(files.ledger, files.statement);
      setDirty(false);
      if (result.replaced) setJob(null);
      addToast(
        `${result.message} · ${result.ledger_rows} ledger / ${result.statement_rows} statement rows`,
      );
      onChange();
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setBusy("");
    }
  }
  const active = ["pending", "running"].includes(job?.status);
  const ready =
    source === "synthetic" ||
    (stats?.total_transactions_in_ledger > 0 &&
      stats?.total_transactions_in_statement > 0);
  return (
    <section className="reconcile-card" aria-labelledby="engine-title">
      <div className="reconcile-info">
        <h2 id="engine-title">Compare. Investigate. Resolve.</h2>
        <p>
          {DEMO_MODE
            ? "Inspect a break, test a resolution, or replay the sample results."
            : "Compare two feeds, inspect the rule evidence, and keep your resolutions when you rerun unchanged data."}
        </p>
        <div className="note-callout">
          {source === "synthetic"
            ? "Synthetic data · 5,000 clean payments plus planted discrepancies. FX labels are hypotheses for human review."
            : "Upload UTF-8 CSV files with comparable amount units. Both files are validated before replacement. Limits: 10 MiB and 10,000 rows per file."}
        </div>
      </div>
      {source === "uploaded" &&
        (DEMO_MODE ? (
          <p className="demo-upload-note">
            File uploads require the FastAPI backend. The public demo uses
            fictional sample data; it does not send or reconcile your files.
          </p>
        ) : (
          <div className="upload-panel">
            {[
              ["ledger", "Internal ledger CSV", FileText],
              ["statement", "Bank statement CSV", Landmark],
            ].map(([key, label, Icon]) => (
              <div className="upload-field" key={key}>
                <label htmlFor={`upload-${key}`}>
                  <Icon size={15} /> {label}
                </label>
                <input
                  id={`upload-${key}`}
                  type="file"
                  accept=".csv,text/csv"
                  disabled={!!busy || active}
                  onChange={(event) => {
                    setFiles((previous) => ({
                      ...previous,
                      [key]: event.target.files[0],
                    }));
                    setDirty(true);
                  }}
                />
              </div>
            ))}
            <button
              className="action-btn"
              disabled={!!busy || active || !files.ledger || !files.statement}
              onClick={upload}
            >
              <Upload size={15} />
              {busy === "upload" ? "Validating…" : "Upload both files"}
            </button>
          </div>
        ))}
      {monitorError && (
        <div className="error-message" role="alert">
          {monitorError}
          <button
            className="action-btn"
            onClick={() =>
              restoreJob().catch((error) => setMonitorError(error.message))
            }
          >
            Check status
          </button>
        </div>
      )}
      {!(DEMO_MODE && source === "uploaded") && (
        <div className="run-row">
          <div className="job-status" role="status">
            {job ? (
              <>
                <div className={`status-dot ${job.status}`} />
                <span>
                  {job.status}
                  {job.breaks_detected != null
                    ? ` · ${job.breaks_detected} breaks`
                    : ""}
                </span>
              </>
            ) : (
              <span>
                {ready ? "Ready to compare" : "Upload both files to begin"}
              </span>
            )}
          </div>
          <button
            className="action-btn primary"
            id="btn-run-reconciliation"
            disabled={!!busy || active || !ready || dirty}
            onClick={run}
          >
            <Play size={15} />
            {busy === "run"
              ? "Starting…"
              : DEMO_MODE
                ? "Replay sample results"
                : "Run reconciliation"}
          </button>
        </div>
      )}
    </section>
  );
}
