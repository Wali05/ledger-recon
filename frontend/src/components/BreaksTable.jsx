import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CheckIcon,
  DownloadIcon,
  EmptySheetIcon,
  LinkIcon,
  SearchIcon,
  SplitIcon,
  UndoIcon,
} from "./Icons";
import { useEffect, useRef, useState } from "react";
import { bulkReview, exportBreaks, getBreaks } from "../api";
import { BREAK_LABELS, BREAK_TYPES, CONFIDENCE_LABELS } from "../constants";
import { formatAmount } from "../format";
import BreakTypeBadge from "./BreakTypeBadge";
import ConfidenceBadge from "./ConfidenceBadge";

export const PAGE_SIZE = 25;
const COLUMNS = [
  ["transaction_id", "Transaction"],
  ["break_type", "Break"],
  ["confidence", "Confidence"],
  ["internal_amount", "Ledger", true],
  ["external_amount", "Bank", true],
  ["delta_amount", "Difference", true],
  ["resolved", "Status"],
];
const STATUSES = [
  ["false", "Open"],
  ["true", "Resolved"],
  ["", "All"],
];

function Amount({ value, signed = false }) {
  if (value === null || value === undefined)
    return <td className="amount amount-empty">—</td>;
  const negative = String(value).startsWith("-");
  const zero = /^-?0*(\.0*)?$/.test(String(value));
  const tone = zero
    ? "amount-empty"
    : signed && negative
      ? "amount-negative"
      : signed
        ? "amount-positive"
        : "";
  return <td className={`amount ${tone}`}>{formatAmount(value)}</td>;
}

// What the row was paired with, in a few words under the transaction ID.
function Partner({ record }) {
  const rows = record.related_rows?.length;
  if (record.evidence_side === "many_internal")
    return (
      <span className="txn-sub">
        <SplitIcon size={12} /> settles {rows} ledger rows
      </span>
    );
  if (record.evidence_side === "many_external")
    return (
      <span className="txn-sub">
        <SplitIcon size={12} /> paid in {rows} bank lines
      </span>
    );
  if (record.break_type === "DUPLICATE")
    return (
      <span className="txn-sub">
        extra copy {record.occurrence} ·{" "}
        {record.evidence_side === "internal" ? "ledger" : "bank"}
      </span>
    );
  if (record.evidence_side !== "pair")
    return (
      <span className="txn-sub">
        {record.evidence_side === "internal" ? "ledger only" : "bank only"}
      </span>
    );
  if (
    record.external_transaction_id &&
    record.external_transaction_id !== record.transaction_id
  )
    return (
      <span className="txn-sub">
        <LinkIcon size={12} /> {record.external_transaction_id}
      </span>
    );
  return <span className="txn-sub">same reference</span>;
}

const typing = (target) =>
  target instanceof HTMLElement &&
  (target.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export default function BreaksTable({
  source,
  filters,
  setFilters,
  onSelectBreak,
  refreshSignal,
  onChanged,
  addToast,
}) {
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState(filters.q);
  const [selected, setSelected] = useState(() => new Set());
  const [active, setActive] = useState(-1);
  const [bulkNote, setBulkNote] = useState("");
  const [busy, setBusy] = useState("");
  const searchRef = useRef(null);
  const tableRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getBreaks({ ...filters, source, page_size: PAGE_SIZE }, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        if (filters.page > 1 && !result.items.length && result.total > 0) {
          setFilters((previous) => ({ ...previous, page: 1 }));
        } else {
          setData(result);
          setActive((index) => Math.min(index, result.items.length - 1));
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [filters, source, refreshSignal, setFilters]);

  // A new view starts with nothing selected.
  useEffect(() => {
    setSelected(new Set());
    setActive(-1);
  }, [filters, source]);

  // Debounce typing into the search box.
  useEffect(() => {
    if (search === filters.q) return;
    const timer = setTimeout(
      () => setFilters((previous) => ({ ...previous, q: search, page: 1 })),
      250,
    );
    return () => clearTimeout(timer);
  }, [search, filters.q, setFilters]);
  useEffect(() => setSearch(filters.q), [filters.q]);

  // Keyboard review: / search, j/k move, Enter open, x select.
  const keys = useRef();
  keys.current = (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (document.querySelector("dialog[open]") || typing(event.target)) return;
    const items = data.items;
    if (event.key === "/") {
      event.preventDefault();
      searchRef.current?.focus();
    } else if (event.key === "j" || event.key === "k") {
      if (!items.length) return;
      event.preventDefault();
      setActive((index) =>
        event.key === "j"
          ? Math.min(index + 1, items.length - 1)
          : Math.max(index - 1, 0),
      );
    } else if ((event.key === "Enter" || event.key === "o") && items[active]) {
      event.preventDefault();
      onSelectBreak(items[active].break_id);
    } else if (event.key === "x" && items[active]) {
      event.preventDefault();
      toggle(items[active].break_id);
    }
  };
  useEffect(() => {
    const listener = (event) => keys.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
  useEffect(() => {
    tableRef.current
      ?.querySelector("tbody tr.active")
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function toggle(id) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  const pageIds = data.items.map((item) => item.break_id);
  const allSelected =
    pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  function toggleAll() {
    setSelected((previous) => {
      const next = new Set(previous);
      for (const id of pageIds) {
        if (allSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  async function bulk(action) {
    setBusy(action);
    try {
      const result = await bulkReview(action, [...selected], bulkNote);
      addToast(
        result.unchanged
          ? `${result.message}; ${result.unchanged} already ${action === "resolve" ? "resolved" : "open"}`
          : result.message,
      );
      setSelected(new Set());
      setBulkNote("");
      onChanged();
    } catch (error) {
      addToast(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function download() {
    try {
      const blob = await exportBreaks({
        source,
        break_type: filters.break_type,
        resolved: filters.resolved,
        confidence: filters.confidence,
        q: filters.q,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `reconciliation_breaks_${source}.csv`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      addToast(error.message, "error");
    }
  }
  function sort(field) {
    setFilters((previous) => ({
      ...previous,
      page: 1,
      sort_by: field,
      sort_dir:
        previous.sort_by === field && previous.sort_dir === "asc"
          ? "desc"
          : "asc",
    }));
  }
  const update = (change) =>
    setFilters((previous) => ({ ...previous, page: 1, ...change }));
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const first = data.total ? (filters.page - 1) * PAGE_SIZE + 1 : 0;
  const last = Math.min(filters.page * PAGE_SIZE, data.total);
  const filtered =
    filters.break_type !== "ALL" || filters.confidence || filters.q;

  return (
    <section className="panel queue" aria-labelledby="breaks-title">
      <header className="queue-head">
        <div>
          <h2 id="breaks-title" className="queue-title">
            Review queue{" "}
            <span className="queue-count">{data.total.toLocaleString()}</span>
          </h2>
          <p className="panel-hint">
            Sorted least certain first. Press <kbd>?</kbd> for shortcuts.
          </p>
        </div>
        <div className="status-tabs" role="group" aria-label="Status">
          {STATUSES.map(([value, label]) => (
            <button
              key={label}
              aria-pressed={filters.resolved === value}
              className={filters.resolved === value ? "active" : ""}
              onClick={() => update({ resolved: value })}
            >
              {label}
            </button>
          ))}
        </div>
      </header>

      <div className="toolbar">
        <label className="search">
          <SearchIcon size={15} />
          <span className="sr-only">Search transactions</span>
          <input
            ref={searchRef}
            type="search"
            placeholder="Search ID, bank reference or evidence"
            value={search}
            maxLength={100}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") event.currentTarget.blur();
            }}
          />
          <kbd aria-hidden="true">/</kbd>
        </label>
        <label className="sr-only" htmlFor="break-type">
          Break type
        </label>
        <select
          className="filter-select"
          id="break-type"
          value={filters.break_type}
          onChange={(event) => update({ break_type: event.target.value })}
        >
          <option value="ALL">All break types</option>
          {BREAK_TYPES.map((type) => (
            <option key={type} value={type}>
              {BREAK_LABELS[type]}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="confidence-filter">
          Confidence
        </label>
        <select
          className="filter-select"
          id="confidence-filter"
          value={filters.confidence}
          onChange={(event) => update({ confidence: event.target.value })}
        >
          <option value="">Any confidence</option>
          {Object.entries(CONFIDENCE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label} confidence
            </option>
          ))}
        </select>
        <button className="action-btn" onClick={download}>
          <DownloadIcon size={15} />
          Export CSV
        </button>
      </div>

      {selected.size > 0 && (
        <div className="bulk-bar" role="region" aria-label="Bulk review">
          <strong>{selected.size} selected</strong>
          <label className="sr-only" htmlFor="bulk-note">
            Note for the selected breaks
          </label>
          <input
            id="bulk-note"
            className="bulk-note"
            placeholder="Note for the record (optional)"
            maxLength={1000}
            value={bulkNote}
            onChange={(event) => setBulkNote(event.target.value)}
          />
          <button
            className="action-btn success"
            disabled={!!busy}
            onClick={() => bulk("resolve")}
          >
            <CheckIcon size={15} />
            {busy === "resolve" ? "Resolving…" : "Resolve selected"}
          </button>
          <button
            className="action-btn"
            disabled={!!busy}
            onClick={() => bulk("reopen")}
          >
            <UndoIcon size={15} />
            Reopen
          </button>
          <button
            className="action-btn ghost"
            onClick={() => setSelected(new Set())}
          >
            Clear
          </button>
        </div>
      )}

      {error ? (
        <p className="error-message" role="alert">
          Could not load breaks: {error}
        </p>
      ) : loading && !data.items.length ? (
        <div className="loading-wrap" role="status">
          <div className="spinner" />
          Loading breaks…
        </div>
      ) : !data.items.length ? (
        <div className="empty-state">
          <EmptySheetIcon size={34} />
          <h3>
            {filters.resolved === "false" && !filtered && data.total === 0
              ? "Nothing left to review"
              : "No breaks to show"}
          </h3>
          <p>
            {source === "uploaded" && !filtered
              ? "Upload both files and run reconciliation to see breaks here."
              : filtered
                ? "Nothing matches these filters."
                : "Run reconciliation, or switch the status tab."}
          </p>
          {filtered && (
            <button
              className="action-btn"
              onClick={() => {
                setSearch("");
                update({ break_type: "ALL", confidence: "", q: "" });
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div
          className={`table-scroll ${loading ? "is-loading" : ""}`}
          ref={tableRef}
        >
          <table>
            <caption className="sr-only">
              Detected discrepancies, sorted across all pages
            </caption>
            <thead>
              <tr>
                <th scope="col" className="select-col">
                  <input
                    type="checkbox"
                    aria-label="Select all on this page"
                    checked={allSelected}
                    onChange={toggleAll}
                  />
                </th>
                {COLUMNS.map(([field, label, numeric]) => (
                  <th
                    key={field}
                    scope="col"
                    className={numeric ? "num" : undefined}
                    aria-sort={
                      filters.sort_by === field
                        ? filters.sort_dir === "asc"
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                  >
                    <button className="sort-button" onClick={() => sort(field)}>
                      {label}
                      <span aria-hidden="true" className="sort-mark">
                        {filters.sort_by === field
                          ? filters.sort_dir === "asc"
                            ? "↑"
                            : "↓"
                          : "↕"}
                      </span>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.map((record, index) => (
                <tr
                  key={record.break_id}
                  className={[
                    "break-row",
                    index === active ? "active" : "",
                    selected.has(record.break_id) ? "selected" : "",
                    record.resolved ? "is-resolved" : "",
                  ].join(" ")}
                  style={{
                    "--badge": `var(--type-${record.break_type.toLowerCase()})`,
                  }}
                  onClick={(event) => {
                    setActive(index);
                    if (!event.target.closest("button, input, label"))
                      onSelectBreak(record.break_id);
                  }}
                >
                  <td className="select-col">
                    <input
                      type="checkbox"
                      aria-label={`Select ${record.transaction_id}`}
                      checked={selected.has(record.break_id)}
                      onChange={() => toggle(record.break_id)}
                    />
                  </td>
                  <td>
                    <button
                      className="txn-id"
                      aria-label={`View break for ${record.transaction_id}`}
                      onClick={() => onSelectBreak(record.break_id)}
                    >
                      {record.transaction_id}
                    </button>
                    <Partner record={record} />
                  </td>
                  <td>
                    <BreakTypeBadge type={record.break_type} />
                  </td>
                  <td>
                    <ConfidenceBadge level={record.confidence} />
                  </td>
                  <Amount value={record.internal_amount} />
                  <Amount value={record.external_amount} />
                  <Amount value={record.delta_amount} signed />
                  <td>
                    <span
                      className={`badge badge-${record.resolved ? "resolved" : "unresolved"}`}
                    >
                      {record.resolved ? "Resolved" : "Open"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <footer className="pagination">
        <span className="pagination-info">
          {data.total
            ? `${first.toLocaleString()}–${last.toLocaleString()} of ${data.total.toLocaleString()} · page ${filters.page} of ${pages}`
            : "No results"}
        </span>
        <div className="pagination-btns">
          <button
            className="action-btn"
            disabled={loading || filters.page <= 1}
            onClick={() =>
              setFilters((previous) => ({
                ...previous,
                page: previous.page - 1,
              }))
            }
          >
            <ChevronLeftIcon size={15} />
            Previous
          </button>
          <button
            className="action-btn"
            disabled={loading || filters.page >= pages}
            onClick={() =>
              setFilters((previous) => ({
                ...previous,
                page: previous.page + 1,
              }))
            }
          >
            Next
            <ChevronRightIcon size={15} />
          </button>
        </div>
      </footer>
    </section>
  );
}
