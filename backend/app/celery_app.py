"""
Celery application configuration.

Broker  : Redis (redis://redis:6379/0) — message queue for task dispatch
Backend : Redis (redis://redis:6379/1) — stores task result state (pending/running/success/failure)

WHY CELERY/REDIS INSTEAD OF SYNCHRONOUS PROCESSING:
  Reconciling large datasets (5,000+ rows) involves:
    1. Loading the full internal ledger from PostgreSQL (a table scan)
    2. Reading the external bank statement CSV
    3. Running O(n) exact matching and up to O(n²) fuzzy matching
    4. Bulk-inserting potentially hundreds of break records to PostgreSQL

  If this were done synchronously inside a FastAPI request handler:
    - The ASGI event loop thread would be blocked for the entire duration.
    - The HTTP client would be left waiting, and most clients (browsers, API gateways)
      time out after 30–60 seconds. With 50,000 rows this would reliably time out.
    - Under concurrent load, multiple synchronous reconciliation requests would
      compete for the same thread pool, degrading all API endpoints.

  With Celery:
    - POST /reconcile/run returns a job_id in ~5ms.
    - The actual heavy work runs in an isolated worker process.
    - The web tier remains responsive; clients poll GET /reconcile/status/{job_id}.
    - The worker can be scaled independently of the API tier.
    - If a worker is lost mid-task, the message is redelivered (task_acks_late +
      task_reject_on_worker_lost). Note: application-level errors are NOT auto-retried
      today — the task records the failure on the job row and re-raises. Auto-retry
      would be safe to add later since the insert is idempotent (see ON CONFLICT below).

  Why Redis as the broker (vs RabbitMQ)?
    - Simpler ops for a single-node development stack.
    - Redis already needed for result storage.
    - In production, RabbitMQ or AWS SQS would be preferred for durability guarantees,
      since Redis pub/sub messages are lost if Redis restarts. Documented limitation.
"""

import os
from celery import Celery

# ── Optional broker ──────────────────────────────────────────────────────────
# If CELERY_BROKER_URL is set we behave exactly as described above: the API
# enqueues, a separate worker process executes.
#
# If it is NOT set, we switch Celery into "eager" mode, where .apply_async()
# runs the task inline in the calling process and returns a finished result.
# That makes the whole project runnable with zero infrastructure — no Redis,
# no worker container — while keeping ONE code path: the endpoint still calls
# reconciliation_task.apply_async() either way, so nothing downstream branches
# on whether a broker exists.
#
# Trade-off, stated plainly: in eager mode the HTTP request blocks for the
# duration of the reconciliation, which is exactly the behaviour the async
# design exists to avoid. It is a convenience for local runs and demos, not a
# production configuration. Set CELERY_BROKER_URL to get the real thing.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "").strip()
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "").strip()
EAGER_MODE = not CELERY_BROKER_URL

celery_app = Celery(
    "ledger_recon",
    broker=CELERY_BROKER_URL or None,
    backend=CELERY_RESULT_BACKEND or None,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Redeliver the message if the worker dies mid-task (not the same as retrying on
    # application errors — see reconciliation_task, which records the failure instead).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # With no broker, run tasks inline and surface their exceptions to the caller.
    task_always_eager=EAGER_MODE,
    task_eager_propagates=EAGER_MODE,
)
