# Ledger Reconciliation Engine

Detects, classifies and explains discrepancies between an internal financial ledger and an external bank statement — the process banks and asset managers call **reconciliation**, and each discrepancy a **break**.

Reconciliation is one of the highest-volume back-office problems in financial services. Two systems that are supposed to agree rarely do: fees get deducted in transit, settlements lag, feeds duplicate rows, foreign-exchange conversion introduces sub-cent drift. This project automates finding those differences across 5,000+ transactions, labels *why* each one broke, and — importantly — measures how often it gets that wrong.

```
┌──────────────────┐        ┌──────────────────┐
│ Internal ledger  │        │  Bank statement  │
│  (what we think) │        │ (what they say)  │
└────────┬─────────┘        └─────────┬────────┘
         └───────────┬────────────────┘
                     ▼
          ┌─────────────────────┐
          │  Matching engine    │   phase 0  duplicates
          │  (pure function)    │   phase 1  exact id match
          └──────────┬──────────┘   phase 2  fuzzy fallback
                     ▼
        130 classified breaks · overall F1 0.885
```

---

## Quickstart

**No database, no Redis, no Docker, no cloud account.**

```bash
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload
```

Then open <http://localhost:8000/docs> and press **POST /reconcile/run** → **Execute**.

With no `DATABASE_URL` set, the app creates a local SQLite file and runs reconciliation jobs in-process. That is a deliberate design choice — see [Deployment](#deployment) — so anyone can clone the repo and watch it work in under a minute.

To see the dashboard as well:

```bash
cd frontend && npm install && npm run dev
```

<details>
<summary><b>Full production architecture instead (Postgres + Redis + a real Celery worker)</b></summary>

```bash
docker compose up --build
```

Frontend on `:5173`, API on `:8000`. The app picks up `DATABASE_URL` and `CELERY_BROKER_URL` from compose and switches from the in-process fallback to a genuine queue-and-worker split — same code, no branching at the call site.
</details>

---

## The matching engine

The core is [`backend/app/engine/matcher.py`](backend/app/engine/matcher.py). `run_matching()` is a **pure function**: two lists in, a list of `BreakRecord` out. No database, no network, no global state — which is why it can be unit-tested directly and why re-running it is trivially safe.

**Phase 0 — duplicate detection.** Scan each feed for repeated `transaction_id`s. The first occurrence stays in the pool for matching; every extra copy is flagged `DUPLICATE`. This runs first because matching with duplicates still present makes "which copy matched?" ambiguous and corrupts everything downstream.

**Phase 1 — exact ID match.** Build a dict of external rows keyed by `transaction_id`, then do one O(1) lookup per internal row — O(n) overall rather than the O(n²) of nested scans. Each matched pair is then interrogated in a fixed order:

1. *Do the amounts agree?* If not → `AMOUNT_MISMATCH`, unless the gap is ≤ $0.05 **and** the currency is non-USD, in which case → `FX_ROUNDING`.
2. *Do the dates agree?* (checked only when amounts are clean) 1–3 days apart → `TIMING_LAG`; further apart → `UNKNOWN`, since that is outside the window where a settlement-lag explanation is credible.

**Phase 2 — fuzzy fallback.** Rows with no ID partner get a second chance, paired on *evidence* instead of identity: amount within $0.50 **and** date within 3 days. This recovers transactions whose IDs were mangled or omitted by the bank's system. The algorithm is **greedy** — first candidate within tolerance wins.

**Leftovers.** Still unpaired after both phases: present only internally → `MISSING_EXTERNAL`; present only externally → `MISSING_INTERNAL`. The name states which side is *missing*, not which side was found.

### Tolerances, and why these numbers

| Constant | Value | Reasoning |
|---|---|---|
| `AMOUNT_TOLERANCE` | ±$0.50 | Covers typical bank fee deductions without pairing genuinely unrelated transactions |
| `DATE_TOLERANCE_DAYS` | ±3 days | T+2 settlement standard, plus one day of weekend buffer |
| `FX_DELTA_THRESHOLD` | ≤$0.05 | FX rounding artifacts are typically sub-cent; $0.05 is deliberately conservative |

Amounts are handled as `Decimal`, never `float`. `0.05` has no exact binary floating-point representation, and on borderline comparisons that error is enough to flip a classification — not acceptable in code that reasons about money.

---

## Evaluation

The headline result is **overall F1 = 0.885**, and the most important thing about it is that it is *not* 1.000.

```
Break Type          GT   Pred   TP   FP   FN   Precision   Recall      F1
AMOUNT_MISMATCH     45     50   40   10    5       0.800    0.889   0.842
MISSING_INTERNAL    15     15   15    0    0       1.000    1.000   1.000
MISSING_EXTERNAL    15     15   15    0    0       1.000    1.000   1.000
DUPLICATE           20     20   20    0    0       1.000    1.000   1.000
TIMING_LAG          15     15   15    0    0       1.000    1.000   1.000
FX_ROUNDING         20     15   10    5   10       0.667    0.500   0.571
─────────────────────────────────────────────────────────────────────────
OVERALL            130    130  115   15   15       0.885    0.885   0.885
```

Reproduce it with:

```bash
python scripts/evaluate_standalone.py
```

### Why the FX number is low on purpose

An earlier version of this project scored a perfect 1.000 on every break type. That was a **circular evaluation**, not a good engine.

The generator planted FX breaks with a delta in `[0.01, 0.04]` and always a non-USD currency. The detector classified FX as delta `≤ 0.05` and non-USD. The planted set was a strict subset of the detection boundary, so a perfect score was *geometrically guaranteed* — the test could not fail, which means it was measuring nothing.

The fix was to make the test data adversarial. [`generate_data.py`](backend/data/generate_data.py) now plants three noise categories specifically designed to defeat the detector:

| Category | Ground truth | What the engine does | Effect |
|---|---|---|---|
| Non-USD row with a genuine small **fee** (delta ≤ $0.05) | `AMOUNT_MISMATCH` | calls it `FX_ROUNDING` | false positive |
| Real FX on a volatile day (delta $0.08–$0.35) | `FX_ROUNDING` | delta > threshold → `AMOUNT_MISMATCH` | false negative |
| Real FX booked to a **USD-normalised** ledger | `FX_ROUNDING` | currency flag lost → `AMOUNT_MISMATCH` | false negative |

`FX_ROUNDING` F1 fell from 1.000 to 0.571, and that number is worth more than the perfect one because it reflects the detector's actual generalisation. Ground truth is assigned at *generation* time from known intent, never inferred from the same amount/date features the engine later reads.

The corollary matters operationally: **a reconciliation run that reports zero breaks should raise suspicion, not confidence.** Real feeds are messy; a clean result more often means a broken pipeline than perfect books.

---

## Idempotency

Reconciliation must be safely repeatable — an ops user retrying a job must not double-count anything, and must not lose work a human has already done.

This is enforced **at the database level**, not in application code:

```sql
UNIQUE (transaction_id, break_type, source)
```

combined with `INSERT ... ON CONFLICT DO NOTHING` in [`tasks.py`](backend/app/tasks.py). A second run over unchanged data inserts zero rows, and any break a human marked resolved in between is left untouched — no application bug or concurrent worker can bypass a constraint the database itself holds.

The engine is deterministic (same input → same set of natural keys), which is what makes that constraint meaningful. Both properties are asserted in the test suite.

**One deliberate exception:** the *uploaded* data path clears its previous breaks before each run, because uploading a new CSV pair replaces the dataset wholesale — stale breaks from a prior upload lingering in the table would be worse than losing resolutions on data that no longer exists.

---

## Testing

```bash
cd backend && pytest tests -v      # 18 unit tests against the engine
python scripts/smoke_test.py       # runs the engine over the full synthetic feed
python scripts/evaluate_standalone.py
```

The unit tests cover every break type, both fuzzy-match tolerance boundaries, the FX/USD distinction, duplicate counting, and determinism.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/reconcile/run?source=synthetic\|uploaded` | Queue a run, returns `job_id` (HTTP 202) |
| `GET` | `/reconcile/status/{job_id}` | Poll job state |
| `POST` | `/reconcile/upload/ledger` | Upload an internal ledger CSV |
| `POST` | `/reconcile/upload/statement` | Upload a bank statement CSV |
| `GET` | `/breaks` | List breaks — filter by type/resolved, paginated |
| `GET` | `/breaks/{break_id}` | Single break detail |
| `POST` | `/breaks/{break_id}/resolve` | Mark resolved (idempotent) |
| `GET` | `/breaks/export` | CSV export of the current filter |
| `POST` | `/breaks/{break_id}/ai-explain` | Gemini-generated plain-English explanation (rate limited, cached) |
| `GET` | `/stats` | Aggregate counts and resolution rate |
| `GET` | `/health` | Liveness probe |

Interactive docs at `/docs`.

### Why reconciliation runs in a background worker

Phase 2 is O(n²) in the worst case. At 5,000 unmatched rows that is 25 million comparisons — seconds of pure CPU. Inside an async FastAPI handler, blocking work of that shape stalls the **entire event loop**, not just the one request, so every concurrent client is degraded and browsers begin timing out at 30–60 seconds.

Celery moves the work into a separate OS process. `POST /reconcile/run` returns a `job_id` in milliseconds, the client polls for completion, and the worker scales independently of the web tier.

*Redis was chosen as the broker over RabbitMQ for operational simplicity in a single-node stack. Redis offers weaker delivery guarantees — messages can be lost on restart — so a production deployment would prefer RabbitMQ or SQS. Documented, not hidden.*

---

## Two operating modes

**Synthetic dataset** — 5,000 clean transactions plus 130 deliberately planted breaks with a known ground-truth map. This is the only mode where precision/recall are meaningful, and the source of every number above.

**CSV upload** — upload your own ledger and statement pair and run the *same* engine against them. No ground truth exists for arbitrary uploads, so this mode reports detected breaks only and is labelled "unevaluated" in the UI. The two datasets live in separate tables and are separated by a `source` column, so uploads can never contaminate the evaluated baseline.

---

## Deployment

The app follows [twelve-factor](https://12factor.net/config) config: **everything comes from the environment, and every variable has a working default.**

| Variable | Unset behaviour | Set behaviour |
|---|---|---|
| `DATABASE_URL` | local SQLite file | Postgres (async + sync drivers derived from the one url) |
| `CELERY_BROKER_URL` | tasks run in-process (eager) | real queue, separate worker |
| `REDIS_URL` | in-memory rate-limit counters | shared counters across processes |
| `ALLOWED_ORIGINS` | localhost dev origins | explicit CORS allow-list |
| `GEMINI_API_KEY` | AI explain button disabled | AI explanations enabled |
| `PORT` | 8000 | platform-assigned port |

Two details make this genuinely portable rather than nominally so. First, a **single** `DATABASE_URL` is accepted and both drivers are derived from it — managed platforms inject exactly one connection string, never two. Second, the legacy `postgres://` scheme that Render, Railway, Heroku and Supabase still emit is rewritten to `postgresql://`, which SQLAlchemy 2.x otherwise refuses to parse. UUID columns use a portable type that maps to native `uuid` on Postgres and `CHAR(36)` elsewhere.

A [`render.yaml`](render.yaml) blueprint is included for a free one-click deploy (database, Redis, API and worker provisioned together, connection strings wired automatically). It is entirely optional — nothing in the codebase depends on a particular host.

---

## Known limitations

Stated plainly, because a system whose failure modes are undocumented cannot be trusted:

1. **Fuzzy matching is greedy, not optimal.** Optimal assignment is the Hungarian algorithm at O(n³) — too expensive for large feeds. Greedy can mis-pair when several unmatched rows share similar amounts and dates.
2. **FX detection depends on a currency flag that production systems often discard.** Ledgers that normalise to USD at booking time lose the signal entirely and those breaks degrade to `AMOUNT_MISMATCH`. Measured, not theoretical: it is half the FX recall loss.
3. **Tolerances are fixed constants, not learned.** A per-counterparty or per-corridor model would adapt; these do not.
4. **Timing-lag uses a fixed 3-day window.** International wires and holiday weekends legitimately exceed it and get misfiled as `UNKNOWN`.
5. **A transaction with both an amount *and* a date discrepancy is classified only by amount.** First classification wins.
6. **Duplicate detection keys on `transaction_id` alone.** A bank re-presenting the same payment under a fresh ID is invisible to it.
7. **Synthetic data understates real-world messiness** — encoding quirks, inconsistent date formats, free-text descriptions, partial settlements.
8. **No authentication or multi-tenancy.** Every caller sees every break.
9. **Schema is created via `create_all`, not migrations.** Fine for a fresh deploy; a long-lived production database would need Alembic.
10. **Single-node design** — no HA, no distributed tracing, no partitioning of the breaks table.

---

## Layout

```
backend/
  app/
    engine/matcher.py     ← the core; pure, dependency-free, unit-tested
    api/reconcile.py      ← run, status, CSV upload
    api/breaks.py         ← list, detail, resolve, export, AI explain
    tasks.py              ← Celery task + idempotent bulk insert
    models.py             ← ORM schema, portable UUID, unique constraint
    database.py           ← one url in, async + sync engines out
  data/generate_data.py   ← synthetic generator with adversarial FX noise
  tests/test_matcher.py   ← 18 unit tests
scripts/
  evaluate_standalone.py  ← per-type precision/recall/F1
  smoke_test.py           ← engine over the full feed, no DB required
frontend/src/App.jsx      ← dashboard, chart, table, upload, detail modal
render.yaml               ← optional free one-click deploy
```

## Stack

FastAPI · SQLAlchemy 2.0 (async) · Celery · Redis · PostgreSQL / SQLite · React + Vite · Recharts · Docker Compose · Google Gemini
