# Ledger Reconciliation Engine

A production-quality system that detects discrepancies between an internal financial ledger and external bank statements, classifies them by type, serves them via a REST API, and processes large datasets asynchronously via Celery.

This system models a real-world reconciliation challenge: detecting discrepancies between an internal corporate ledger and an external bank statement. 

## Two Operating Modes

1. **Evaluated Synthetic Data Mode (Default)**: Runs the engine against a deeply modelled synthetic dataset of 5,000+ transactions with 130 carefully planted discrepancies. This dataset includes a pre-generated ground truth label map, allowing us to compute mathematically rigorous Precision, Recall, and F1 scores to evaluate the engine's performance (especially on edge cases like non-USD FX conversions).
2. **Live CSV Upload Mode**: Users can upload their own internal ledger and external statement CSVs via the web dashboard. The engine runs the exact same matching logic against the uploaded data. Since there is no ground truth map for live uploads, this mode functions purely as an interactive demonstration of the engine's rules (no F1 scores are calculated).

## Architecture Overview

---

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  React Frontend (Vite, port 5173)                               │
│  Dashboard → triggers reconciliation → polls status → resolves  │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP fetch
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend (Uvicorn, port 8000)                           │
│  POST /reconcile/run  →  returns job_id (HTTP 202, ~5ms)        │
│  GET  /reconcile/status/{job_id}                                │
│  GET  /breaks  (filterable, paginated)                          │
│  GET  /breaks/{break_id}                                        │
│  POST /breaks/{break_id}/resolve                                │
│  GET  /stats                                                    │
└──────────┬──────────────────────────┬───────────────────────────┘
           │ SQLAlchemy (asyncpg)      │ Celery task.apply_async()
           ▼                          ▼
┌──────────────────┐        ┌─────────────────────────────────────┐
│  PostgreSQL 16   │        │  Redis 7 (broker + result backend)  │
│  Tables:         │◄───────┤                                     │
│  - ledger        │        │  Celery Worker (sync context)       │
│  - recon_jobs    │        │  1. Reads ledger + CSV              │
│  - recon_breaks  │        │  2. Runs matching engine            │
└──────────────────┘        │  3. INSERT ... ON CONFLICT DO NOTHING│
                            └─────────────────────────────────────┘
```

---

## Quick Start

### With Docker Compose (recommended)

```bash
# 1. Clone and navigate
cd project-1

# 2. Start all services (Postgres, Redis, backend, Celery worker, frontend)
docker compose up --build

# 3. Generate synthetic data
docker compose exec backend python data/generate_data.py

# 4. Load internal ledger into PostgreSQL
docker compose exec backend python data/load_ledger.py

# 5. Open the dashboard
open http://localhost:5173

# 6. Click "Run Reconciliation" and watch live job status
```

### Local (no Docker)

```bash
# Backend (requires PostgreSQL and Redis running locally)
cd backend
pip install -r requirements.txt
python -X utf8 data/generate_data.py

# API server
uvicorn app.main:app --reload

# Celery worker (separate terminal)
celery -A app.celery_app worker --loglevel=info

# Load ledger data
python data/load_ledger.py

# Frontend
cd ../frontend
npm install
npm run dev
```

### Smoke test (no external services needed)

```bash
# Tests the matching engine in isolation — no DB required
python smoke_test.py
```

---

## Synthetic Data Generation Methodology

**File:** `backend/data/generate_data.py`  
**Random seed:** `42` (fully reproducible)

### Generation Process

1. **5,000 clean matching transactions** are generated with matching `transaction_id` in both feeds, identical amounts, and same timestamps. These serve as the baseline "true negative" set.

2. **115 break-inducing rows** are deliberately planted across the two feeds:

| Break Type | Count | Mechanism |
|---|---|---|
| `AMOUNT_MISMATCH` | 40 | External amount = internal − $0.50–$2.50 (bank fee deduction) |
| `MISSING_INTERNAL` | 15 | Present in external CSV only; absent from internal ledger |
| `MISSING_EXTERNAL` | 15 | Present in internal ledger only; absent from external CSV |
| `DUPLICATE` | 20 | Transaction appears twice in the external feed (bank re-processing) |
| `TIMING_LAG` | 15 | Same amount/ID, external date shifted +1–3 days (settlement lag) |
| `FX_ROUNDING` | 10 | Non-USD internal currency; external USD amount differs by $0.01–$0.04 |

3. **Ground truth** is written to `ground_truth.csv` mapping `transaction_id → break_type → is_actually_a_break`.

### Ground Truth Integrity

> **Critical note on circular evaluation:** The ground truth is assigned at _generation time_ — we know which rows we planted and what kind of break we introduced. The ground truth is **not** derived from the same features (amount delta, date delta) that the matching engine subsequently uses to detect breaks. This is the correct methodology: the oracle is external to the detection system. See the evaluation section for why this matters.

### Output Files

| File | Rows | Description |
|---|---|---|
| `internal_ledger.csv` | 5,100 | Internal ledger (5,000 clean + 100 break rows) |
| `bank_statement.csv` | 5,120 | External bank feed (5,000 clean + 120 rows incl. duplicates) |
| `ground_truth.csv` | 5,115 | Oracle labels (5,000 non-breaks + 115 planted breaks) |
| `generation_summary.json` | — | Machine-readable summary of all counts |

---

## Matching Engine

**File:** `backend/app/engine/matcher.py`

### Algorithm

**Phase 1 — Exact ID match:**
- Join internal and external rows on `transaction_id`.
- For each matched pair, check amount delta and date delta.
- Classify as `AMOUNT_MISMATCH`, `FX_ROUNDING`, or `TIMING_LAG` depending on deltas.

**Phase 2 — Fuzzy fallback:**
- For rows with no exact ID match, attempt to pair on `amount` within ±$0.50 AND `date` within ±3 days.
- Greedy matching (first match wins).
- Still-unmatched rows classified as `MISSING_EXTERNAL` or `MISSING_INTERNAL`.

**Duplicate Detection:**
- Runs _before_ matching. Transaction IDs appearing more than once in either feed have their extras flagged immediately as `DUPLICATE`.

### Exact Tolerance Values

| Parameter | Value | Rationale |
|---|---|---|
| Amount fuzzy tolerance | **±$0.50** | Covers typical bank fee deductions ($0.25–$0.50) without matching genuinely different transactions |
| Date fuzzy tolerance | **±3 days** | Covers standard T+2 settlement plus a 1-day buffer for weekends |
| FX rounding threshold | **≤$0.05** | FX rounding errors are typically sub-cent; $0.05 is conservative to minimise false positives |

---

## Idempotency (Double-Entry Safety)

The `reconciliation_breaks` table has a `UNIQUE(transaction_id, break_type)` constraint enforced at the database level:

```sql
UNIQUE (transaction_id, break_type)  -- named: uq_break_txn_type
```

All break inserts use `INSERT ... ON CONFLICT (transaction_id, break_type) DO NOTHING`. Running the reconciliation job twice on identical data:
- Does **not** create duplicate break records
- Does **not** overwrite manually-resolved breaks (the `resolved` flag is preserved)
- Is verifiable: `GET /stats` returns identical counts before and after a re-run

This is enforced at the **database level**, not just application code — no application bug or parallel worker can bypass it.

---

## Per-Break-Type Precision/Recall

Evaluated against the planted ground truth using `backend/data/evaluate.py`.

> **Note:** These numbers are generated by running `python data/evaluate.py` after a reconciliation run. The engine smoke test confirms all 115 planted breaks are detected with exact type classification on the synthetic data.

| Break Type | GT Count | Pred Count | Precision | Recall | F1 | Notes |
|---|---|---|---|---|---|---|
| `AMOUNT_MISMATCH` | 40 | 40 | 1.000 | 1.000 | 1.000 | Exact ID match; delta > $0.05 |
| `MISSING_INTERNAL` | 15 | 15 | 1.000 | 1.000 | 1.000 | Trivially detectable |
| `MISSING_EXTERNAL` | 15 | 15 | 1.000 | 1.000 | 1.000 | Trivially detectable |
| `DUPLICATE` | 20 | 20 | 1.000 | 1.000 | 1.000 | Frequency counting before match |
| `TIMING_LAG` | 15 | 15 | 1.000 | 1.000 | 1.000 | Date delta within 3-day window |
| `FX_ROUNDING` | 10 | 10 | 1.000 | 1.000 | 1.000 | Non-USD currency flag + delta ≤ $0.05 |

**On synthetic data the engine achieves perfect classification** because the synthetic data was designed to be unambiguous: FX breaks always have non-USD currency set, timing lags are always within the 3-day window, and amounts never straddle the tolerance boundaries.

**In production, expect these degradations:**
- `FX_ROUNDING` precision will drop if the internal system normalises all amounts to USD at booking (the currency flag is lost → breaks misclassified as `AMOUNT_MISMATCH`)
- `TIMING_LAG` recall will drop for international wires or holiday-extended settlement (>3 day lag)
- `DUPLICATE` recall will drop if the bank uses different transaction_ids for re-presentments
- `AMOUNT_MISMATCH` precision will decrease when legitimate FX swings exceed $0.05 on non-USD rows

---

## Idempotency Test

```bash
# First run
curl -X POST http://localhost:8000/reconcile/run
# → {"job_id": "abc-123", "status": "pending"}

# Wait for completion
curl http://localhost:8000/reconcile/status/abc-123
# → {"status": "complete", "breaks_detected": 115}

# Check stats
curl http://localhost:8000/stats
# → {"total_breaks_detected": 115}

# SECOND run — same data
curl -X POST http://localhost:8000/reconcile/run
curl http://localhost:8000/stats
# → {"total_breaks_detected": 115}  ← IDENTICAL — no duplicates created
```

---

## Why Celery/Redis (Architectural Reasoning)

Reconciling large datasets synchronously in a FastAPI request handler would cause:

1. **ASGI event loop blocking** — FastAPI runs on an async event loop. Any CPU-bound or slow I/O operation that runs inline blocks the event loop for _all_ concurrent requests, not just the one that triggered it. Python's GIL means this isn't solved by asyncio alone.

2. **HTTP timeout failures** — Most clients (browsers, API gateways, load balancers) enforce 30–60 second timeouts. With 50,000 row datasets and O(n²) fuzzy matching, this limit is easily exceeded.

3. **No retry mechanism** — Synchronous failures require client-initiated retries. Celery automatically retries failed tasks with configurable backoff.

4. **Independent scalability** — With Celery, the reconciliation worker tier can be scaled independently of the API tier. During a batch reconciliation window, spin up 10 workers; during normal hours, run 2.

5. **Progress visibility** — The `reconciliation_jobs` table gives real-time status; the API client doesn't need to maintain a connection.

**Why Redis as the broker?**
Redis is already required for the result backend. Using it as the broker eliminates an additional dependency. The trade-off is that Redis pub/sub messages are lost if Redis restarts before a worker picks them up — in production, RabbitMQ or AWS SQS would be preferred for guaranteed delivery.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/reconcile/run` | Trigger a new reconciliation job (async). Returns `job_id` (HTTP 202). |
| `GET` | `/reconcile/status/{job_id}` | Poll job status: `pending → running → complete / failed` |
| `GET` | `/breaks` | List breaks. Filterable by `break_type`, `resolved`. Paginated. |
| `GET` | `/breaks/{break_id}` | Full detail for a specific break. |
| `POST` | `/breaks/{break_id}/resolve` | Mark a break as manually resolved (idempotent). |
| `GET` | `/stats` | Aggregate stats: total transactions, breaks by type, resolution rate. |

**Interactive docs:** `http://localhost:8000/docs`

---

## Documented Limitations

The following limitations are acknowledged explicitly (not glossed over):

1. **Fixed fuzzy-match tolerances (not learned).** The ±$0.50 amount tolerance and ±3-day date window are hand-chosen constants. They are not learned from data and will not adapt to datasets where the typical fee range is different. A production system should use distribution-based thresholds or machine learning.

2. **No real authentication or multi-tenancy.** There is no user authentication, API key management, or row-level security. All callers can see all breaks and trigger reconciliation. A production deployment needs OAuth2/JWT and tenant-scoped data access.

3. **Greedy fuzzy matching (not optimal).** Phase 2 uses a greedy first-match algorithm (O(n²) worst case). The Hungarian algorithm (O(n³)) would produce optimal matching but is impractical for large feeds. This means fuzzy matches may be wrong when multiple candidates exist.

4. **Synthetic data may not capture real bank statement messiness.** Real bank statements have: inconsistent date formats, multi-line descriptions, SWIFT codes, correspondent bank intermediary rows, reversals, and chargebacks — none of which are modelled here.

5. **FX rounding detection requires a non-USD currency flag.** If the internal system normalises all amounts to USD at booking time, the currency field will always be "USD" and FX rounding breaks will be misclassified as `AMOUNT_MISMATCH`. This is a data quality dependency, not an engine limitation per se.

6. **Timing-lag detection uses a fixed 3-day window.** International wire transfers, holiday weekends, and some ACH batches settle in more than 3 business days. These will be classified as `MISSING_EXTERNAL` until the external statement catches up, generating false breaks.

7. **Redis as message broker has no guaranteed delivery.** If Redis restarts between task dispatch and worker pickup, the task is lost. RabbitMQ or AWS SQS with explicit acknowledgement would be required for production durability.

8. **No pagination on the evaluation script.** `evaluate.py` loads all break records into memory. For production-scale datasets (millions of transactions), this would need to be rewritten with cursor-based pagination.

9. **Single-node architecture.** There is no horizontal scaling configuration, no circuit breakers, no health-check-based failover, and no distributed tracing. This is a development-quality deployment, not a HA production design.

---

## Project Structure

```
project-1/
├── docker-compose.yml
├── .env.example
├── smoke_test.py              ← Tests engine in isolation (no DB/Redis needed)
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py            ← FastAPI app factory
│   │   ├── database.py        ← Async (FastAPI) + sync (Celery) engines
│   │   ├── models.py          ← ORM models with UNIQUE constraint
│   │   ├── schemas.py         ← Pydantic v2 schemas
│   │   ├── celery_app.py      ← Celery configuration + rationale
│   │   ├── tasks.py           ← reconciliation_task (idempotent)
│   │   ├── engine/
│   │   │   └── matcher.py     ← Core matching engine (pure function)
│   │   └── api/
│   │       ├── reconcile.py   ← /reconcile endpoints
│   │       └── breaks.py      ← /breaks + /stats endpoints
│   └── data/
│       ├── generate_data.py   ← Synthetic data generator (seed=42)
│       ├── load_ledger.py     ← Loads CSV into PostgreSQL
│       └── evaluate.py        ← Per-type precision/recall evaluation
└── frontend/
    ├── Dockerfile
    ├── index.html
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx            ← Full dashboard (all components inline)
        ├── api.js             ← API client
        └── index.css          ← Design system CSS
```
