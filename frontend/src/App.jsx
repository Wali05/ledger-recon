import {
  ArrowUpRightIcon,
  BrandMark,
  LedgerIcon,
  UndoIcon,
  UploadIcon,
} from "./components/Icons";
import { useCallback, useEffect, useRef, useState } from "react";
import { DEMO_MODE, getSession, getStats, resetDemo, setApiKey } from "./api";
import BreakDetailModal from "./components/BreakDetailModal";
import BreaksChart from "./components/BreaksChart";
import BreaksTable from "./components/BreaksTable";
import ReconcileControl from "./components/ReconcileControl";
import SignIn from "./components/SignIn";
import StatsCards from "./components/StatsCards";
import Toast from "./components/Toast";
import "./index.css";

const REPO = "https://github.com/Wali05/ledger-recon";

export default function App() {
  const [source, setSource] = useState("synthetic");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [demoReset, setDemoReset] = useState(0);
  const [selectedBreak, setSelectedBreak] = useState(null);
  const [toasts, setToasts] = useState([]);
  // undefined = checking, null = signed out, otherwise { auth_required, reviewer }
  const [session, setSession] = useState(undefined);
  const [signInError, setSignInError] = useState("");
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

  const checkSession = useCallback(async () => {
    try {
      const current = await getSession();
      setSession(current.auth_required && !current.reviewer ? null : current);
      return current;
    } catch {
      // API unreachable: show the normal connection error instead of sign-in.
      setSession({ auth_required: false, reviewer: null });
      return null;
    }
  }, []);
  useEffect(() => {
    checkSession();
    const signOut = () => {
      setApiKey("");
      setSession(null);
    };
    window.addEventListener("ledger-recon:unauthorized", signOut);
    return () =>
      window.removeEventListener("ledger-recon:unauthorized", signOut);
  }, [checkSession]);
  async function signIn(key) {
    setApiKey(key);
    const current = await checkSession();
    if (current?.reviewer) {
      setSignInError("");
      refresh();
    } else {
      setApiKey("");
      setSignInError("That key was not accepted.");
    }
  }

  const ready = session !== undefined && session !== null;
  useEffect(() => {
    if (!ready) return;
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
  }, [source, refreshSignal, ready]);

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

  const ledgerRows = stats?.total_transactions_in_ledger;
  const statementRows = stats?.total_transactions_in_statement;
  return (
    <div className="app">
      <nav className="navbar" aria-label="Workspace">
        <a className="navbar-brand" href="/">
          <BrandMark />
          Ledger Recon
        </a>
        {ready && (
          <div className="nav-section">
            <span className="nav-heading">Dataset</span>
            <div className="seg-toggle" role="group" aria-label="Dataset">
              <button
                className={`seg-btn ${source === "synthetic" ? "active" : ""}`}
                aria-pressed={source === "synthetic"}
                onClick={() => changeSource("synthetic")}
              >
                <LedgerIcon size={18} />
                Sample dataset
              </button>
              <button
                className={`seg-btn ${source === "uploaded" ? "active" : ""}`}
                aria-pressed={source === "uploaded"}
                onClick={() => changeSource("uploaded")}
              >
                <UploadIcon size={18} />
                Your CSV files
              </button>
            </div>
          </div>
        )}
        <div className="navbar-meta">
          <span className="mode-line">
            <span className={`mode-indicator ${DEMO_MODE ? "demo" : ""}`} />
            <span>
              {DEMO_MODE ? "Interactive demo" : "Connected workspace"}
            </span>
          </span>
          {!DEMO_MODE && session?.auth_required && session.reviewer && (
            <span className="reviewer-chip">
              {session.reviewer}
              <button
                onClick={() => {
                  setApiKey("");
                  setSession(null);
                }}
              >
                Sign out
              </button>
            </span>
          )}
          <a
            className="source-link"
            href={REPO}
            target="_blank"
            rel="noreferrer"
          >
            <ArrowUpRightIcon size={15} />
            <span>Source on GitHub</span>
          </a>
        </div>
      </nav>

      <main>
        {session === null ? (
          <SignIn onSubmit={signIn} error={signInError} />
        ) : session === undefined ? (
          <div className="loading-wrap" role="status">
            <div className="spinner" />
            Connecting
          </div>
        ) : (
          <>
            <header className="page-head">
              <div>
                <p className="eyebrow">
                  {source === "synthetic" ? "Sample dataset" : "Your CSV files"}
                </p>
                <h1 className="page-title">Ledger against bank statement</h1>
                <p className="page-sub">
                  {ledgerRows && statementRows
                    ? `${ledgerRows.toLocaleString()} ledger rows compared with ${statementRows.toLocaleString()} statement rows. Every break keeps its evidence until someone resolves it.`
                    : "Compare an internal ledger with a bank statement, inspect each break's evidence and record who resolved it."}
                </p>
              </div>
            </header>
            {DEMO_MODE && (
              <div className="demo-banner">
                <p>
                  <strong>Interactive demo.</strong> These breaks were produced
                  by the Python matcher. Your review decisions stay in this
                  browser.
                </p>
                <button className="action-btn" onClick={reset}>
                  <UndoIcon size={14} />
                  Reset demo
                </button>
              </div>
            )}
            {error && (
              <p className="error-message connection-error" role="alert">
                Could not reach the API: {error}. Start the backend, then retry.
                <button className="action-btn" onClick={refresh}>
                  Retry
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
            {stats?.breaks_by_type?.length > 0 && <BreaksChart stats={stats} />}
            {source === "uploaded" && stats?.total_breaks_detected > 0 && (
              <p className="dataset-caption">
                Uploaded files have no answer key, so these counts describe what
                was found, not how accurate it is.
              </p>
            )}
            <BreaksTable
              key={`breaks-${source}-${demoReset}`}
              source={source}
              onSelectBreak={setSelectedBreak}
              refreshSignal={refreshSignal}
              addToast={addToast}
            />
            <footer className="project-footer">
              <span>
                Deterministic rules decide; people resolve. Nothing here moves
                money.
              </span>
              <a href={`${REPO}#how-it-works`}>How the matcher works</a>
            </footer>
          </>
        )}
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
