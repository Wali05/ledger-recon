import { useEffect, useRef, useState } from "react";
import { Check, Sparkles, X } from "lucide-react";
import { getBreak, resolveBreak, explainBreakWithAI, DEMO_MODE } from "../api";
import { formatAmount, formatDate } from "../format";
import BreakTypeBadge from "./BreakTypeBadge";

export default function BreakDetailModal({
  breakId,
  onClose,
  onResolved,
  addToast,
  aiEnabled,
}) {
  const dialogRef = useRef(null);
  const [record, setRecord] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    getBreak(breakId, controller.signal)
      .then(setRecord)
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, [breakId]);

  async function resolve() {
    setBusy("resolve");
    try {
      const result = await resolveBreak(breakId);
      setRecord((previous) => ({ ...previous, ...result }));
      addToast(DEMO_MODE ? "Resolved in your browser demo" : "Break resolved");
      onResolved();
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setBusy("");
    }
  }
  async function explain() {
    setBusy("ai");
    try {
      const result = await explainBreakWithAI(breakId);
      setRecord((previous) => ({
        ...previous,
        ai_explanation: result.explanation,
      }));
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setBusy("");
    }
  }
  const fields = record
    ? [
        ["Transaction ID", record.transaction_id],
        ["External transaction", record.external_transaction_id || "—"],
        [
          "Internal amount",
          formatAmount(record.internal_amount, record.currency),
        ],
        [
          "External amount",
          formatAmount(record.external_amount, record.currency),
        ],
        ["Difference", formatAmount(record.delta_amount, record.currency)],
        ["Currency", record.currency || "Not supplied by statement"],
        ["Internal date", formatDate(record.internal_timestamp)],
        ["External date", formatDate(record.external_timestamp)],
        ["Detected", formatDate(record.detected_at)],
        ["Resolved", formatDate(record.resolved_at)],
        [
          "Evidence",
          record.evidence_side === "pair"
            ? "Matched pair"
            : `${record.evidence_side} feed${record.occurrence ? " · extra occurrence " + record.occurrence : ""}`,
        ],
        ["Break ID", record.break_id],
      ]
    : [];
  return (
    <dialog
      ref={dialogRef}
      className="modal modal-dialog"
      onCancel={onClose}
      aria-labelledby="detail-title"
      onClick={(event) => {
        const box = event.currentTarget.getBoundingClientRect();
        if (
          event.clientX < box.left ||
          event.clientX > box.right ||
          event.clientY < box.top ||
          event.clientY > box.bottom
        )
          onClose();
      }}
    >
      <div className="modal-header">
        <h2 id="detail-title" className="modal-title">
          Break detail
        </h2>
        <button
          className="modal-close"
          aria-label="Close break details"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </div>
      <div className="modal-body">
        {error ? (
          <p role="alert" className="error-message">
            {error}
          </p>
        ) : !record ? (
          <div className="loading-wrap" role="status">
            Loading break…
          </div>
        ) : (
          <>
            <div className="detail-badges">
              <BreakTypeBadge type={record.break_type} />
              <span
                className={`badge badge-${record.resolved ? "resolved" : "unresolved"}`}
              >
                {record.resolved ? "Resolved" : "Open"}
              </span>
            </div>
            <dl className="detail-grid">
              {fields.map(([label, value]) => (
                <div key={label} className="detail-item">
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
              <div className="detail-item span-2">
                <dt>Rule evidence</dt>
                <dd>{record.description}</dd>
              </div>
            </dl>
            {(aiEnabled || record.ai_explanation) && (
              <div className="ai-panel">
                <div className="ai-panel-head">
                  <span>
                    <Sparkles size={14} /> Optional explanation
                  </span>
                  {aiEnabled && !record.ai_explanation && (
                    <button
                      className="action-btn"
                      onClick={explain}
                      disabled={!!busy}
                    >
                      {busy === "ai" ? "Generating…" : "Ask AI to explain"}
                    </button>
                  )}
                </div>
                <p className="ai-hint">
                  {record.ai_explanation ||
                    (aiEnabled
                      ? "A generated explanation suggests possible causes. Verify them before resolving."
                      : "Rule evidence is available above. AI explanations are disabled in this session.")}
                </p>
              </div>
            )}
          </>
        )}
      </div>
      <div className="modal-footer">
        <button className="action-btn ghost" onClick={onClose}>
          Close
        </button>
        {record && !record.resolved && (
          <button
            className="action-btn success"
            disabled={!!busy}
            onClick={resolve}
          >
            <Check size={15} />
            {busy === "resolve" ? "Resolving…" : "Mark resolved"}
          </button>
        )}
      </div>
    </dialog>
  );
}
