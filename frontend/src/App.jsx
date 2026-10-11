import { useCallback, useEffect, useRef, useState } from "react";
import { Scale, ExternalLink, RotateCcw } from "lucide-react";
import { DEMO_MODE, getStats, resetDemo } from "./api";
import BreakDetailModal from "./components/BreakDetailModal";
import ReconcileControl from "./components/ReconcileControl";
import StatsCards from "./components/StatsCards";
import BreaksTable from "./components/BreaksTable";
import Toast from "./components/Toast";
import BreaksChart from "./components/BreaksChart";
import "./index.css";

export default function App() {
  const [source, setSource] = useState("synthetic");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [demoReset, setDemoReset] = useState(0);
  const [selectedBreak, setSelectedBreak] = useState(null);
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Set());
  const addToast = useCallback((message, type = "success") => {
    const id = crypto.randomUUID();
    setToasts((previous) => [...previous, { id, message, type }]);
    const timer = setTimeout(() => {
      setToasts((previous) => previous.filter((toast) => toast.id !== id));
      timers.current.delete(timer);
    }, 5500);
    timers.current.add(timer);
  }, []);
  useEffect(() => {
    const activeTimers = timers.current;
    return () => activeTimers.forEach(clearTimeout);
  }, []);
  const refresh = useCallback(() => setRefreshSignal((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    getStats(source, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setStats(data);
      })
      .catch((error) => {
        if (error.name !== "AbortError") setError(error.message);
      });
    return () => controller.abort();
  }, [source, refreshSignal]);
  function changeSource(value) {
    setSource(value);
    setStats(null);
    setSelectedBreak(null);
  }
  async function reset() {
    await resetDemo();
    setSelectedBreak(null);
    setDemoReset((value) => value + 1);
    refresh();
    addToast("Demo review state reset");
  }
  return (
    <div className="app">
      <nav className="navbar" aria-label="Project navigation">
        <a className="navbar-brand" href="/">
          <span className="logo-icon">
            <Scale size={19} />
          </span>
          <span>Ledger Recon</span>
        </a>
        <div className="navbar-meta">
          <span className={`mode-indicator ${DEMO_MODE ? "demo" : ""}`} />
          <span>{DEMO_MODE ? "Interactive demo" : "Connected workspace"}</span>
          <a
            className="source-link"
            href="https://github.com/Wali05/ledger-recon"
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink size={16} />
            Source
          </a>
        </div>
      </nav>
      <main>
        <div className="page-head">
          <div>
            <p className="eyebrow">FINANCIAL OPERATIONS / RECONCILIATION</p>
            <h1 className="page-title">
              Every difference <em>accounted for.</em>
            </h1>
            <p className="page-sub">
              Find discrepancies between a ledger and bank statement. Inspect
              the evidence before you resolve.
            </p>
          </div>
          <div className="seg-toggle" aria-label="Dataset">
            <button
              className={`seg-btn ${source === "synthetic" ? "active" : ""}`}
              aria-pressed={source === "synthetic"}
              onClick={() => changeSource("synthetic")}
            >
              Sample dataset
            </button>
            <button
              className={`seg-btn ${source === "uploaded" ? "active" : ""}`}
              aria-pressed={source === "uploaded"}
              onClick={() => changeSource("uploaded")}
            >
              Your CSV files
            </button>
          </div>
        </div>
        {DEMO_MODE && (
          <div className="demo-banner">
            <div>
              <strong>Sample results, real matching rules.</strong>
              <p>
                The Python engine generated these discrepancies. Replaying loads
                the saved results; resolution choices are local to this browser.
              </p>
            </div>
            <button className="action-btn" onClick={reset}>
              <RotateCcw size={14} />
              Reset demo
            </button>
          </div>
        )}
        {error && (
          <p className="error-message connection-error" role="alert">
            API unavailable: {error}. Start the backend or use the demo build.
            <button className="action-btn" onClick={refresh}>
              Retry connection
            </button>
          </p>
        )}
        <ReconcileControl
          key={`control-${source}-${demoReset}`}
          source={source}
          stats={stats}
          onChange={refresh}
          addToast={addToast}
        />
        <StatsCards stats={stats} />
        {source === "uploaded" && (
          <p className="dataset-caption">
            Uploaded data has no labelled ground truth. These counts describe
            detected discrepancies, not accuracy.
          </p>
        )}
        {stats?.breaks_by_type?.length > 0 && <BreaksChart stats={stats} />}
        <BreaksTable
          key={`breaks-${source}-${demoReset}`}
          source={source}
          onSelectBreak={setSelectedBreak}
          refreshSignal={refreshSignal}
          addToast={addToast}
        />
        <footer className="project-footer">
          <span>
            Deterministic rules. Human review. No automatic payment changes.
          </span>
          <a href="https://github.com/Wali05/ledger-recon">
            Explore the implementation ↗
          </a>
        </footer>
      </main>
      {selectedBreak && (
        <BreakDetailModal
          key={selectedBreak}
          breakId={selectedBreak}
          onClose={() => setSelectedBreak(null)}
          onResolved={refresh}
          addToast={addToast}
          aiEnabled={stats?.ai_enabled}
        />
      )}
      <Toast toasts={toasts} />
    </div>
  );
}
