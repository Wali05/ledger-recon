import {
  BankIcon,
  CheckIcon,
  CloseIcon,
  HistoryIcon,
  SheetIcon,
  SparkIcon,
  SplitIcon,
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
import { CONFIDENCE_HINTS } from "../constants";
import {
  dayGap,
  formatAmount,
  formatDate,
  formatDay,
  scaled,
  unscaled,
} from "../format";
import BreakTypeBadge from "./BreakTypeBadge";
import ConfidenceBadge from "./ConfidenceBadge";

// The two sides as a reviewer would compare them, with the cells that
// disagree marked. Group members are listed with their running total.
function Comparison({ record }) {
  if (record.break_type === "DUPLICATE") {
    const ledger = record.evidence_side === "internal";
    return (
      <div className="compare duplicate-note">
        <p>
          Extra copy {record.occurrence} of <code>{record.transaction_id}</code>{" "}
          in the {ledger ? "ledger" : "bank statement"}. The first copy was
          matched normally; this one has nothing left to pair with.
        </p>
        <p className="mono">
          {formatAmount(
            ledger ? record.internal_amount : record.external_amount,
            record.currency,
          )}{" "}
          ·{" "}
          {formatDay(
            ledger ? record.internal_timestamp : record.external_timestamp,
          )}
        </p>
      </div>
    );
  }
  const side = record.evidence_side;
  const many = side.startsWith("many_");
  const ledgerRef =
    side === "external"
      ? null
      : side === "many_internal"
        ? `${record.related_rows?.length || 0} rows`
        : record.transaction_id;
  const bankRef =
    side === "internal"
      ? null
      : side === "many_external"
        ? `${record.related_rows?.length || 0} lines`
        : record.external_transaction_id;
  const gap = dayGap(record.internal_timestamp, record.external_timestamp);
  const delta = record.delta_amount && scaled(record.delta_amount);
  const rows = [
    [
      "Reference",
      ledgerRef,
      bankRef,
      ledgerRef && bankRef && ledgerRef !== bankRef && !many ? "differs" : null,
    ],
    [
      "Amount",
      record.internal_amount != null
        ? formatAmount(record.internal_amount, record.currency)
        : null,
      record.external_amount != null
        ? formatAmount(record.external_amount)
        : null,
      delta ? formatAmount(record.delta_amount) : null,
    ],
    [
      "Date",
      record.internal_timestamp ? formatDay(record.internal_timestamp) : null,
      record.external_timestamp ? formatDay(record.external_timestamp) : null,
      gap ? `${gap} day${gap === 1 ? "" : "s"}` : null,
    ],
  ];
  return (
    <div className="compare">
      <table className="compare-table">
        <thead>
          <tr>
            <th scope="col">
              <span className="sr-only">Field</span>
            </th>
            <th scope="col">
              <SheetIcon size={14} /> Ledger
            </th>
            <th scope="col">
              <BankIcon size={14} /> Bank
            </th>
            <th scope="col" className="num">
              Difference
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, ledger, bank, difference]) => (
            <tr key={label} className={difference ? "differs" : ""}>
              <th scope="row">{label}</th>
              <td className={ledger ? "" : "absent"}>
                {ledger || "Not in ledger"}
              </td>
              <td className={bank ? "" : "absent"}>{bank || "Not at bank"}</td>
              <td className="num">
                {difference ? (
                  <span className="diff-chip">{difference}</span>
                ) : (
                  <span className="tie-mark">ties</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {many && <Members record={record} />}
    </div>
  );
}

function Members({ record }) {
  const ledgerSide = record.evidence_side === "many_internal";
  const members = record.related_rows || [];
  const total = members.reduce((sum, row) => sum + scaled(row.amount), 0n);
  const target = ledgerSide ? record.external_amount : record.internal_amount;
  const ties = total === scaled(target);
  return (
    <section className="members" aria-labelledby="members-title">
      <h3 id="members-title">
        <SplitIcon size={14} />
        {ledgerSide
          ? `${members.length} ledger rows settled by this bank line`
          : `${members.length} bank lines that pay this ledger row`}
      </h3>
      <ol>
        {members.map((row) => (
          <li key={row.transaction_id}>
            <span className="mono">{row.transaction_id}</span>
            <span className="muted">{formatDay(row.timestamp)}</span>
            <span className="mono num">{formatAmount(row.amount)}</span>
          </li>
        ))}
      </ol>
      <p className={`members-total ${ties ? "ties" : ""}`}>
        <span>Sum</span>
        <span className="mono num">
          {formatAmount(unscaled(total))} {ties ? "= " : "≠ "}
          {formatAmount(target)}
        </span>
      </p>
    </section>
  );
}

export default function BreakDrawer({
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
  const action = record?.resolved ? "reopen" : "resolve";
  return (
    <dialog
      ref={dialogRef}
      className="drawer"
      onCancel={onClose}
      aria-labelledby="detail-title"
      onKeyDown={(event) => {
        if (
          event.key === "Enter" &&
          (event.metaKey || event.ctrlKey) &&
          record &&
          !busy
        ) {
          event.preventDefault();
          review(action);
        }
      }}
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
      <header className="drawer-head">
        <div>
          <p className="eyebrow">Break evidence</p>
          <h2 id="detail-title" className="drawer-title">
            {record ? record.transaction_id : "Loading…"}
          </h2>
        </div>
        <button
          className="icon-btn"
          aria-label="Close evidence"
          onClick={onClose}
        >
          <CloseIcon size={16} />
        </button>
      </header>
      <div className="drawer-body">
        {error ? (
          <p role="alert" className="error-message">
            {error}
          </p>
        ) : !record ? (
          <div className="loading-wrap" role="status">
            <div className="spinner" />
            Loading break…
          </div>
        ) : (
          <>
            <div className="detail-badges">
              <BreakTypeBadge type={record.break_type} />
              <ConfidenceBadge level={record.confidence} />
              <span
                className={`badge badge-${record.resolved ? "resolved" : "unresolved"}`}
              >
                {record.resolved ? "Resolved" : "Open"}
              </span>
            </div>
            <section className="why" aria-labelledby="why-title">
              <h3 id="why-title">Why it was flagged</h3>
              <p>{record.description}</p>
              {record.confidence && (
                <p className="muted">{CONFIDENCE_HINTS[record.confidence]}</p>
              )}
            </section>
            <Comparison record={record} />
            <dl className="meta-grid">
              <div>
                <dt>Detected</dt>
                <dd>{formatDate(record.detected_at)}</dd>
              </div>
              <div>
                <dt>Resolved</dt>
                <dd>
                  {record.resolved_at
                    ? `${formatDate(record.resolved_at)} by ${record.resolved_by || "unknown"}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>Currency</dt>
                <dd>{record.currency || "Not on the statement"}</dd>
              </div>
              <div>
                <dt>Break ID</dt>
                <dd className="mono small">{record.break_id}</dd>
              </div>
            </dl>
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
                <p className="muted">
                  {record.ai_explanation ||
                    "A generated explanation suggests possible causes. Verify them before resolving."}
                </p>
              </div>
            )}
            <section className="history" aria-labelledby="history-title">
              <h3 id="history-title">
                <HistoryIcon size={14} /> Review history
              </h3>
              {events.length ? (
                <ol className="history-list">
                  {events.map((event) => (
                    <li key={event.event_id} className={event.action}>
                      <span className="history-action">{event.action}</span> by{" "}
                      <strong>{event.reviewer}</strong>
                      <time dateTime={event.created_at}>
                        {formatDate(event.created_at)}
                      </time>
                      {event.note && (
                        <p className="history-note">{event.note}</p>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted">No review decisions yet.</p>
              )}
            </section>
          </>
        )}
      </div>
      {record && (
        <footer className="drawer-foot">
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
          <div className="drawer-actions">
            <span className="muted small">
              <kbd>Ctrl</kbd> + <kbd>Enter</kbd> to {action}
            </span>
            <button className="action-btn ghost" onClick={onClose}>
              Close
            </button>
            {record.resolved ? (
              <button
                className="action-btn"
                disabled={!!busy}
                onClick={() => review("reopen")}
              >
                <UndoIcon size={15} />
                {busy === "reopen" ? "Reopening…" : "Reopen"}
              </button>
            ) : (
              <button
                className="action-btn success"
                disabled={!!busy}
                onClick={() => review("resolve")}
              >
                <CheckIcon size={15} />
                {busy === "resolve" ? "Resolving…" : "Mark resolved"}
              </button>
            )}
          </div>
        </footer>
      )}
    </dialog>
  );
}
