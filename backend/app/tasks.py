"""
Celery tasks for the Ledger Reconciliation Engine.

IDEMPOTENCY GUARANTEE:
  reconciliation_task uses INSERT ... ON CONFLICT DO NOTHING when writing break
  records to the database. The UNIQUE(transaction_id, break_type) constraint on the
  reconciliation_breaks table ensures that re-running the same reconciliation on
  unchanged data produces no duplicate breaks.

  The job record itself is created by the API layer before dispatching the task,
  so the task only needs to update the existing job row's status.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.engine.matcher import load_internal_ledger, load_external_statement, run_matching

# Path to the data files (inside the container, /app/data/)
DATA_DIR = Path(__file__).parent.parent / "data"


def _utcnow():
    return datetime.now(timezone.utc)


@celery_app.task(bind=True, name="app.tasks.reconciliation_task")
def reconciliation_task(self, job_id: str, source: str = "synthetic"):
    """
    Main reconciliation background task.

    Flow:
      1. Mark job as 'running' in the database.
      2. Load internal ledger from PostgreSQL (via CSV for simplicity — in production
         this would be a direct DB query with pagination).
      3. Load external bank statement from CSV.
      4. Run the matching engine.
      5. Bulk-insert detected breaks using ON CONFLICT DO NOTHING.
      6. Mark job as 'complete'.

    Error handling: any unhandled exception marks the job as 'failed' with the
    error message stored for API retrieval.

    WHY THIS RUNS IN CELERY (not inline in FastAPI):
      The matching engine's Phase 2 fuzzy matching is O(n²) in the worst case —
      for 5,000 unmatched rows that would be 25 million comparisons. Even at
      microsecond speeds, that blocks the calling thread for multiple seconds.
      In a FastAPI async endpoint, any blocking operation blocks the entire event
      loop for all concurrent requests, not just the one that triggered it.
      Celery runs this in a separate OS process, completely isolated from the web tier.
    """
    from sqlalchemy import text
    import uuid as _uuid

    session = SyncSessionLocal()
    job_uuid = _uuid.UUID(job_id)

    try:
        # ── 1. Mark job as running ───────────────────────────────────────────
        session.execute(
            text("""
                UPDATE reconciliation_jobs
                SET status = 'running', started_at = :now
                WHERE job_id = :job_id
            """),
            {"now": _utcnow(), "job_id": job_uuid},
        )
        session.commit()

        # ── 2. Load data ─────────────────────────────────────────────────────
        if source == "synthetic":
            internal_path = DATA_DIR / "internal_ledger.csv"
            external_path = DATA_DIR / "bank_statement.csv"

            if not internal_path.exists() or not external_path.exists():
                raise FileNotFoundError(
                    f"Data files not found. Run backend/data/generate_data.py first. "
                    f"Expected: {internal_path} and {external_path}"
                )

            internal_rows = load_internal_ledger(internal_path)
            external_rows = load_external_statement(external_path)
        else:
            # Load from DB for uploaded data
            from app.engine.matcher import InternalRow, ExternalRow
            from decimal import Decimal

            # Load uploaded internal ledger
            int_res = session.execute(text("SELECT transaction_id, account_id, amount, currency, timestamp, description, status FROM uploaded_ledger"))
            internal_rows = [
                InternalRow(
                    transaction_id=r.transaction_id,
                    account_id=r.account_id,
                    amount=Decimal(r.amount),
                    currency=r.currency,
                    timestamp=r.timestamp,
                    description=r.description or "",
                    status=r.status or "",
                ) for r in int_res.fetchall()
            ]

            # Load uploaded external statement
            ext_res = session.execute(text("SELECT transaction_id, amount, timestamp, description FROM uploaded_statement"))
            external_rows = [
                ExternalRow(
                    transaction_id=r.transaction_id,
                    amount=Decimal(r.amount),
                    timestamp=r.timestamp,
                    description=r.description or "",
                ) for r in ext_res.fetchall()
            ]

        # ── 3. Run matching engine ────────────────────────────────────────────
        breaks = run_matching(internal_rows, external_rows)

        # ── 4. Bulk-insert breaks — idempotent via ON CONFLICT DO NOTHING ─────
        # The UNIQUE(transaction_id, break_type) constraint means a second run on
        # the same data will silently skip all conflicting rows. Existing 'resolved'
        # breaks set by humans are never overwritten by a re-run.
        inserted = 0
        for br in breaks:
            result = session.execute(
                text("""
                    INSERT INTO reconciliation_breaks
                        (break_id, transaction_id, break_type, internal_amount,
                         external_amount, delta_amount, internal_timestamp,
                         external_timestamp, description, detected_at, resolved, job_id, source)
                    VALUES
                        (:break_id, :transaction_id, :break_type, :internal_amount,
                         :external_amount, :delta_amount, :internal_timestamp,
                         :external_timestamp, :description, :detected_at, false, :job_id, :source)
                    ON CONFLICT (transaction_id, break_type, source) DO NOTHING
                """),
                {
                    "break_id": _uuid.uuid4(),
                    "transaction_id": br.transaction_id,
                    "break_type": br.break_type,
                    "internal_amount": float(br.internal_amount) if br.internal_amount is not None else None,
                    "external_amount": float(br.external_amount) if br.external_amount is not None else None,
                    "delta_amount": float(br.delta_amount) if br.delta_amount is not None else None,
                    "internal_timestamp": br.internal_timestamp,
                    "external_timestamp": br.external_timestamp,
                    "description": br.description,
                    "detected_at": _utcnow(),
                    "job_id": job_uuid,
                    "source": source,
                },
            )
            if result.rowcount > 0:
                inserted += 1
        session.commit()

        # ── 5. Update job to complete ─────────────────────────────────────────
        total_internal = len(internal_rows)
        session.execute(
            text("""
                UPDATE reconciliation_jobs
                SET status = 'complete',
                    finished_at = :now,
                    transactions_processed = :processed,
                    breaks_detected = :breaks
                WHERE job_id = :job_id
            """),
            {
                "now": _utcnow(),
                "processed": total_internal,
                "breaks": inserted,
                "job_id": job_uuid,
            },
        )
        session.commit()

        return {
            "job_id": job_id,
            "status": "complete",
            "transactions_processed": total_internal,
            "breaks_detected": inserted,
        }

    except Exception as exc:
        session.rollback()
        session.execute(
            text("""
                UPDATE reconciliation_jobs
                SET status = 'failed',
                    finished_at = :now,
                    error_message = :error
                WHERE job_id = :job_id
            """),
            {"now": _utcnow(), "error": str(exc), "job_id": job_uuid},
        )
        session.commit()
        raise

    finally:
        session.close()
