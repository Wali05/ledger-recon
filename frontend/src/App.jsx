import {
  ArrowUpRightIcon,
  BrandMark,
  KeyboardIcon,
  LedgerIcon,
  MoonIcon,
  SunIcon,
  UndoIcon,
  UploadIcon,
} from "./components/Icons";
import { useCallback, useEffect, useRef, useState } from "react";
import { DEMO_MODE, getSession, getStats, resetDemo, setApiKey } from "./api";
import BreakDrawer from "./components/BreakDrawer";
import BreakMix from "./components/BreakMix";
import BreaksTable from "./components/BreaksTable";
import EnginePanel from "./components/EnginePanel";
import Overview from "./components/Overview";
import ReconcileControl from "./components/ReconcileControl";
import ShortcutsDialog from "./components/ShortcutsDialog";
import SignIn from "./components/SignIn";
import Toast from "./components/Toast";
import "./index.css";

const REPO = "https://github.com/Wali05/ledger-recon";
const THEME_KEY = "ledger-recon.theme";
// The queue opens on what still needs a reviewer, least certain first.
const DEFAULT_FILTERS = {
  page: 1,
  break_type: "ALL",
  resolved: "false",
  confidence: "",
  q: "",
  sort_by: "confidence",
  sort_dir: "asc",
};

function initialTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* Storage disabled: follow the system. */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export default function App() {
  const [source, setSource] = useState("synthetic");
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [refreshSignal, setRefreshSignal] = useState(0);
  const [demoReset, setDemoReset] = useState(0);
  const [selectedBreak, setSelectedBreak] = useState(null);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [toasts, setToasts] = useState([]);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [theme, setTheme] = useState(initialTheme);
  // undefined = checking, null = signed out, otherwise { auth_required, reviewer }
  const [session, setSession] = useState(undefined);
  const [signInError, setSignInError] = useState("");
  const timers = useRef(new Set());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* The choice lasts for this page only. */
    }
  }, [theme]);

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
    function onKey(event) {
      const target = event.target;
      if (
        event.key !== "?" ||
        document.querySelector("dialog[open]") ||
        (target instanceof HTMLElement &&
          ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
      )
        return;
      event.preventDefault();
      setShowShortcuts(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    setFilters(DEFAULT_FILTERS);
  }
  async function reset() {
    await resetDemo();
    setSelectedBreak(null);
    setFilters(DEFAULT_FILTERS);
    setDemoReset((value) => value + 1);
    refresh();
    addToast("Demo review state reset");
  }
  const selectType = useCallback(
    (type) =>
      setFilters((previous) => ({
        ...previous,
        break_type: type,
        page: 1,
      })),
    [],
  );

  const ledgerRows = stats?.total_transactions_in_ledger;
  const statementRows = stats?.total_transactions_in_statement;
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href={import.meta.env.BASE_URL}>
          <BrandMark size={28} />
          <span>Ledger Recon</span>
        </a>
        {ready && (
          <div className="seg-toggle" role="group" aria-label="Dataset">
            <button
              className={source === "synthetic" ? "active" : ""}
              aria-pressed={source === "synthetic"}
              onClick={() => changeSource("synthetic")}
            >
              <LedgerIcon size={16} />
              Sample dataset
            </button>
            <button
              className={source === "uploaded" ? "active" : ""}
              aria-pressed={source === "uploaded"}
              onClick={() => changeSource("uploaded")}
            >
              <UploadIcon size={16} />
              Your CSV files
            </button>
          </div>
        )}
        <div className="topbar-meta">
          <span className={`mode-chip ${DEMO_MODE ? "demo" : "live"}`}>
            <i aria-hidden="true" />
            {DEMO_MODE ? "Interactive demo" : "Connected workspace"}
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
          <button
            className="icon-btn"
            aria-label="Keyboard shortcuts"
            title="Keyboard shortcuts (?)"
            onClick={() => setShowShortcuts(true)}
          >
            <KeyboardIcon size={17} />
          </button>
          <button
            className="icon-btn"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title="Switch theme"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <SunIcon size={17} /> : <MoonIcon size={17} />}
          </button>
          <a
            className="source-link"
            href={REPO}
            target="_blank"
            rel="noreferrer"
          >
            <span>Source</span>
            <ArrowUpRightIcon size={14} />
          </a>
        </div>
      </header>

      <main className="page">
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
              <p className="eyebrow">
                {source === "synthetic" ? "Sample dataset" : "Your CSV files"}
              </p>
              <h1 className="page-title">Ledger against bank statement</h1>
              <p className="page-sub">
                {ledgerRows && statementRows
                  ? `${ledgerRows.toLocaleString()} ledger rows compared with ${statementRows.toLocaleString()} bank lines. Every break keeps the evidence behind it until someone signs it off.`
                  : "Compare an internal ledger with a bank statement, inspect each break's evidence and record who resolved it."}
              </p>
            </header>
            {DEMO_MODE && (
              <div className="demo-banner">
                <p>
                  <strong>Interactive demo.</strong> Real output from the Python
                  matcher, stored as a snapshot. Review decisions stay in this
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
            <Overview stats={stats} />
            {stats?.breaks_by_type?.length > 0 && (
              <div className="insights">
                <BreakMix
                  stats={stats}
                  activeType={filters.break_type}
                  onSelectType={selectType}
                />
                <EnginePanel />
              </div>
            )}
            {source === "uploaded" && stats?.total_breaks_detected > 0 && (
              <p className="dataset-caption">
                Uploaded files have no answer key, so these counts describe what
                was found, not how accurate it is.
              </p>
            )}
            <BreaksTable
              key={`breaks-${source}-${demoReset}`}
              source={source}
              filters={filters}
              setFilters={setFilters}
              onSelectBreak={setSelectedBreak}
              refreshSignal={refreshSignal}
              onChanged={refresh}
              addToast={addToast}
            />
            <footer className="project-footer">
              <span>
                Built with FastAPI, SQLAlchemy, Celery and React. Deterministic
                rules decide; people resolve.
              </span>
              <a href={`${REPO}#how-it-works`}>How the matcher works</a>
            </footer>
          </>
        )}
      </main>
      {selectedBreak && (
        <BreakDrawer
          key={selectedBreak}
          breakId={selectedBreak}
          onClose={() => setSelectedBreak(null)}
          onResolved={refresh}
          addToast={addToast}
          aiEnabled={stats?.ai_enabled}
        />
      )}
      {showShortcuts && (
        <ShortcutsDialog onClose={() => setShowShortcuts(false)} />
      )}
      <Toast toasts={toasts} />
    </div>
  );
}
