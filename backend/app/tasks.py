"""Run the real matcher and publish a job's results in one transaction."""

import logging
import uuid
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.engine.matcher import (
    ExternalRow,
    InternalRow,
    load_external_statement,
    load_internal_ledger,
    run_matching,
)
from app.models import (
    DatasetState,
    ReconciliationBreak,
    ReconciliationJob,
    UploadedLedgerTransaction,
    UploadedStatementTransaction,
    utcnow,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
logger = logging.getLogger(__name__)


def _result(job):
    return {
        "job_id": str(job.job_id),
        "status": job.status,
        "transactions_processed": job.transactions_processed,
        "breaks_detected": job.breaks_detected,
        "breaks_inserted": job.breaks_inserted,
        "breaks_retired": job.breaks_retired,
    }


# Evidence the engine recomputes on every run. Review state (resolution, who and
# when), the break ID, first detection time and cached explanations are kept.
EVIDENCE_FIELDS = (
    "external_transaction_id",
    "currency",
    "internal_amount",
    "external_amount",
    "delta_amount",
    "internal_timestamp",
    "external_timestamp",
    "description",
    "confidence",
    "related_ids",
)


def _publish(session, source, job_id, breaks):
    """Upsert this run's breaks and retire the ones it no longer produces.

    A break's stable key decides whether it is new. Existing breaks keep their
    review state but take the latest evidence, so a rule change never leaves a
    stale explanation behind. Breaks the current rules no longer report are
    deleted; their review events stay in the append-only history.
    """
    existing = dict(
        session.execute(
            select(ReconciliationBreak.break_key, ReconciliationBreak.break_id).where(
                ReconciliationBreak.source == source
            )
        ).all()
    )
    insert_fn = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    current = set()
    for record in breaks:
        current.add(record.identity)
        values = asdict(record)
        values.update(
            break_key=record.identity,
            break_id=uuid.uuid4(),
            source=source,
            job_id=job_id,
            detected_at=utcnow(),
            resolved=False,
        )
        statement = insert_fn(ReconciliationBreak).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["source", "break_key"],
                set_={field: getattr(statement.excluded, field) for field in EVIDENCE_FIELDS},
            )
        )
    stale = [break_id for key, break_id in existing.items() if key not in current]
    for start in range(0, len(stale), 500):
        session.execute(
            delete(ReconciliationBreak).where(
                ReconciliationBreak.break_id.in_(stale[start : start + 500])
            )
        )
    return len(current - existing.keys()), len(stale)


@celery_app.task(bind=True, name="app.tasks.reconciliation_task")
def reconciliation_task(self, job_id: str, source: str = "synthetic"):
    job_uuid = uuid.UUID(job_id)
    with SyncSessionLocal() as session:
        try:
            job = session.get(ReconciliationJob, job_uuid)
            if not job or job.source != source:
                raise ValueError("Job and dataset do not match")
            if job.status == "complete":
                return _result(job)
            session.execute(
                update(ReconciliationJob)
                .where(ReconciliationJob.job_id == job_uuid, ReconciliationJob.status != "complete")
                .values(status="running", started_at=utcnow(), error_message=None)
            )
            session.commit()

            # Lock until results and completion are committed. Redelivered tasks
            # serialize here, then observe the first worker's completed job.
            session.execute(
                update(DatasetState)
                .where(DatasetState.source == source)
                .values(ledger_rows=DatasetState.ledger_rows)
            )
            session.expire_all()
            job = session.get(ReconciliationJob, job_uuid)
            if job.status == "complete":
                return _result(job)

            if source == "synthetic":
                internal = load_internal_ledger(DATA_DIR / "internal_ledger.csv")
                external = load_external_statement(DATA_DIR / "bank_statement.csv")
            elif source == "uploaded":
                internal = [
                    InternalRow(
                        r.transaction_id,
                        r.account_id,
                        r.amount,
                        r.currency,
                        r.timestamp,
                        r.description or "",
                        r.status,
                    )
                    for r in session.scalars(
                        select(UploadedLedgerTransaction).order_by(UploadedLedgerTransaction.row_id)
                    )
                ]
                external = [
                    ExternalRow(
                        r.transaction_id,
                        r.amount,
                        r.timestamp,
                        r.description or "",
                    )
                    for r in session.scalars(
                        select(UploadedStatementTransaction).order_by(
                            UploadedStatementTransaction.row_id
                        )
                    )
                ]
                if not internal or not external:
                    raise ValueError("Both uploaded feeds are required")
            else:
                raise ValueError("Unknown dataset")

            breaks = run_matching(internal, external)
            inserted, retired = _publish(session, source, job_uuid, breaks)
            state = session.get(DatasetState, source)
            state.ledger_rows, state.statement_rows = len(internal), len(external)
            job.status, job.finished_at = "complete", utcnow()
            job.transactions_processed = len(internal)
            job.breaks_detected, job.breaks_inserted = len(breaks), inserted
            job.breaks_retired = retired
            session.commit()
            logger.info(
                "Reconciliation completed: source=%s rows=%s detected=%s inserted=%s retired=%s",
                source,
                len(internal),
                len(breaks),
                inserted,
                retired,
            )
            return _result(job)
        except Exception:
            session.rollback()
            logger.exception("Reconciliation job %s failed", job_id)
            session.execute(
                update(ReconciliationJob)
                .where(ReconciliationJob.job_id == job_uuid, ReconciliationJob.status != "complete")
                .values(
                    status="failed",
                    finished_at=utcnow(),
                    error_message="Reconciliation failed. Check the API or worker logs for details.",
                )
            )
            session.commit()
            raise
