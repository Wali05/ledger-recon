import {
  CheckIcon,
  CloseIcon,
  HistoryIcon,
  SparkIcon,
  UndoIcon,
} from "./Icons";
import { useEffect, useRef, useState } from "react";
import {
  getBreak,
  getBreakEvents,
  resolveBreak,
  reopenBreak,
  explainBreakWithAI,
} from "../api";
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
  const [note, setNote] = useState("");
  const [events, setEvents] = useState([]);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getBreak(breakId, controller.signal),
      getBreakEvents(breakId, controller.signal),
    ])
      .then(([detail, history]) => {
        setRecord(detail);
        setEvents(history);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, [breakId]);

  async function review(action) {
    setBusy(action);
    try {
      const result = await (action === "resolve" ? resolveBreak : reopenBreak)(
        breakId,
        note,
      );
      const { message, ...state } = result;
      setRecord((previous) => ({ ...previous, ...state }));
      setEvents(await getBreakEvents(breakId));
      setNote("");
      addToast(message);
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
        ["Ledger transaction", record.transaction_id],
        ["Bank transaction", record.external_transaction_id || "—"],
        ["Ledger date", formatDate(record.internal_timestamp)],
        ["Bank date", formatDate(record.external_timestamp)],
        ["Currency", record.currency || "Not on the statement"],
        ["Detected", formatDate(record.detected_at)],
        [
          "Resolved",
          record.resolved_at
            ? `${formatDate(record.resolved_at)} by ${record.resolved_by || "unknown"}`
            : "—",
        ],
        [
          "Evidence",
          record.evidence_side === "pair"
            ? "Paired rows"
            : `${record.evidence_side === "internal" ? "Ledger" : "Bank"} side only${record.occurrence ? `, extra copy ${record.occurrence}` : ""}`,
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
          {record ? record.transaction_id : "Break"}
        </h2>
        <button
          className="modal-close"
          aria-label="Close evidence"
          onClick={onClose}
        >
          <CloseIcon size={16} />
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
            <dl className="detail-sum" aria-label="Amounts">
              <dt>Ledger</dt>
              <dd>{formatAmount(record.internal_amount, record.currency)}</dd>
              <dt>Bank</dt>
              <dd>{formatAmount(record.external_amount, record.currency)}</dd>
              <dt className="total">Difference</dt>
              <dd className="total">
                {formatAmount(record.delta_amount, record.currency)}
              </dd>
            </dl>
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
            <section className="review-panel" aria-labelledby="history-title">
              <h3 id="history-title" className="review-title">
                <HistoryIcon size={14} /> Review history
              </h3>
              {events.length ? (
                <ol className="history-list">
                  {events.map((event) => (
                    <li key={event.event_id}>
                      <span className={`history-action ${event.action}`}>
                        {event.action}
                      </span>{" "}
                      by <strong>{event.reviewer}</strong> on{" "}
                      {formatDate(event.created_at)}
                      {event.note && (
                        <p className="history-note">{event.note}</p>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="ai-hint">No review decisions yet.</p>
              )}
              <label className="note-label" htmlFor="review-note">
                Note for the record (optional)
              </label>
              <textarea
                id="review-note"
                className="note-input"
                rows={2}
                maxLength={1000}
                value={note}
                placeholder={
                  record.resolved
                    ? "Why is this being reopened?"
                    : "e.g. Bank fee confirmed with statement line 42"
                }
                onChange={(event) => setNote(event.target.value)}
              />
            </section>
            {(aiEnabled || record.ai_explanation) && (
              <div className="ai-panel">
                <div className="ai-panel-head">
                  <span>
                    <SparkIcon size={14} /> Optional explanation
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
            onClick={() => review("resolve")}
          >
            <CheckIcon size={15} />
            {busy === "resolve" ? "Resolving…" : "Mark resolved"}
          </button>
        )}
        {record?.resolved && (
          <button
            className="action-btn"
            disabled={!!busy}
            onClick={() => review("reopen")}
          >
            <UndoIcon size={15} />
            {busy === "reopen" ? "Reopening…" : "Reopen"}
          </button>
        )}
      </div>
    </dialog>
  );
}
