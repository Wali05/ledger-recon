import {
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  EmptySheetIcon,
} from "./Icons";
import { useEffect, useState } from "react";
import { getBreaks, exportBreaks } from "../api";
import { BREAK_LABELS, BREAK_TYPE_OPTIONS } from "../constants";
import { formatAmount } from "../format";
import BreakTypeBadge from "./BreakTypeBadge";

const PAGE_SIZE = 25;
const COLUMNS = [
  ["transaction_id", "Transaction"],
  ["break_type", "Break"],
  ["internal_amount", "Ledger", true],
  ["external_amount", "Bank", true],
  ["delta_amount", "Difference", true],
  ["resolved", "Status"],
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
      : "";
  return <td className={`amount ${tone}`}>{formatAmount(value)}</td>;
}

export default function BreaksTable({
  source,
  onSelectBreak,
  refreshSignal,
  addToast,
}) {
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({
    page: 1,
    break_type: "ALL",
    resolved: "",
    sort_by: "detected_at",
    sort_dir: "desc",
  });
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getBreaks({ ...filters, source, page_size: PAGE_SIZE }, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        if (filters.page > 1 && !result.items.length && result.total > 0) {
          setFilters((previous) => ({ ...previous, page: 1 }));
        } else setData(result);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [filters, source, refreshSignal]);

  async function download() {
    try {
      const blob = await exportBreaks({
        source,
        break_type: filters.break_type,
        resolved: filters.resolved,
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
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  return (
    <section className="table-wrap" aria-labelledby="breaks-title">
      <div className="table-header">
        <h2 id="breaks-title" className="table-title">
          Breaks{" "}
          <span className="table-count">({data.total.toLocaleString()})</span>
        </h2>
        <div className="table-filters">
          <label className="sr-only" htmlFor="break-type">
            Break type
          </label>
          <select
            className="filter-select"
            id="break-type"
            value={filters.break_type}
            onChange={(event) =>
              setFilters({
                ...filters,
                page: 1,
                break_type: event.target.value,
              })
            }
          >
            {BREAK_TYPE_OPTIONS.map((type) => (
              <option key={type} value={type}>
                {type === "ALL" ? "All break types" : BREAK_LABELS[type]}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="resolution-filter">
            Resolution status
          </label>
          <select
            className="filter-select"
            id="resolution-filter"
            value={filters.resolved}
            onChange={(event) =>
              setFilters({ ...filters, page: 1, resolved: event.target.value })
            }
          >
            <option value="">All statuses</option>
            <option value="false">Open</option>
            <option value="true">Resolved</option>
          </select>
          <button className="action-btn" onClick={download}>
            <DownloadIcon size={15} />
            Export CSV
          </button>
        </div>
      </div>
      {error ? (
        <p className="error-message" role="alert">
          Could not load breaks: {error}
        </p>
      ) : loading ? (
        <div className="loading-wrap" role="status">
          <div className="spinner" />
          Loading breaks…
        </div>
      ) : !data.items.length ? (
        <div className="empty-state">
          <EmptySheetIcon size={34} />
          <h3>No breaks to show</h3>
          <p>
            {source === "uploaded"
              ? "Upload both files and run reconciliation to see breaks here."
              : "Run reconciliation, or clear the filters above."}
          </p>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <caption className="sr-only">
              Detected discrepancies, sorted across all pages
            </caption>
            <thead>
              <tr>
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
                      {label}{" "}
                      <span aria-hidden="true">
                        {filters.sort_by === field
                          ? filters.sort_dir === "asc"
                            ? "↑"
                            : "↓"
                          : "↕"}
                      </span>
                    </button>
                  </th>
                ))}
                <th scope="col">
                  <span className="sr-only">Evidence</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((record) => (
                <tr
                  key={record.break_id}
                  className="break-row"
                  onClick={(event) => {
                    if (!event.target.closest("button"))
                      onSelectBreak(record.break_id);
                  }}
                >
                  <td>
                    <span className="txn-id">{record.transaction_id}</span>
                  </td>
                  <td>
                    <BreakTypeBadge type={record.break_type} />
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
                  <td>
                    <button
                      className="row-open"
                      aria-label={`View break for ${record.transaction_id}`}
                      onClick={() => onSelectBreak(record.break_id)}
                    >
                      Evidence
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination">
        <span className="pagination-info">
          Page {filters.page} of {pages}
        </span>
        <div className="pagination-btns">
          <button
            className="action-btn"
            disabled={loading || filters.page <= 1}
            onClick={() => setFilters({ ...filters, page: filters.page - 1 })}
          >
            <ChevronLeftIcon size={15} />
            Previous
          </button>
          <button
            className="action-btn"
            disabled={loading || filters.page >= pages}
            onClick={() => setFilters({ ...filters, page: filters.page + 1 })}
          >
            Next
            <ChevronRightIcon size={15} />
          </button>
        </div>
      </div>
    </section>
  );
}
