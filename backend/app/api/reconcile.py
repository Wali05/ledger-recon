"""
Reconciliation job endpoints.

POST /reconcile/run   — dispatch a new Celery task, return job_id immediately
GET  /reconcile/status/{job_id} — poll job status from the DB
POST /reconcile/upload/ledger — Upload internal ledger CSV
POST /reconcile/upload/statement — Upload external statement CSV
"""

import csv
import io
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.schemas import ReconcileRunResponse, JobStatusResponse, UploadResponse
from app.tasks import reconciliation_task

router = APIRouter(prefix="/reconcile", tags=["reconciliation"])
logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)

def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.post("/upload/ledger", response_model=UploadResponse)
async def upload_ledger(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session)
):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB.")
    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")
    
    reader = csv.DictReader(io.StringIO(decoded))
    required_cols = {"transaction_id", "account_id", "amount", "currency", "timestamp"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"Missing required columns. Expected: {required_cols}")

    inserted = 0
    skipped = 0

    await session.execute(text("TRUNCATE TABLE uploaded_ledger"))

    for i, row in enumerate(reader, start=1):
        try:
            result = await session.execute(
                text("""
                    INSERT INTO uploaded_ledger
                    (transaction_id, account_id, amount, currency, timestamp, description, status)
                    VALUES (:tid, :aid, :amt, :curr, :ts, :desc, :stat)
                    ON CONFLICT (transaction_id) DO NOTHING
                """),
                {
                    "tid": row["transaction_id"],
                    "aid": row["account_id"],
                    "amt": Decimal(row["amount"]),
                    "curr": row.get("currency", "USD"),
                    "ts": _parse_dt(row["timestamp"]),
                    "desc": row.get("description", ""),
                    "stat": row.get("status", "settled"),
                }
            )
            # rowcount is 0 when ON CONFLICT skipped a duplicate transaction_id.
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            skipped += 1
            logger.warning("Skipping ledger row %d: %s", i, e)

    await session.commit()
    return UploadResponse(message="Ledger uploaded successfully", rows_inserted=inserted, rows_skipped=skipped)


@router.post("/upload/statement", response_model=UploadResponse)
async def upload_statement(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session)
):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB.")
    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")
    
    reader = csv.DictReader(io.StringIO(decoded))
    required_cols = {"transaction_id", "amount", "timestamp"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"Missing required columns. Expected: {required_cols}")

    inserted = 0
    skipped = 0

    await session.execute(text("TRUNCATE TABLE uploaded_statement"))

    for i, row in enumerate(reader, start=1):
        try:
            result = await session.execute(
                text("""
                    INSERT INTO uploaded_statement
                    (transaction_id, amount, timestamp, description)
                    VALUES (:tid, :amt, :ts, :desc)
                    ON CONFLICT (transaction_id) DO NOTHING
                """),
                {
                    "tid": row["transaction_id"],
                    "amt": Decimal(row["amount"]),
                    "ts": _parse_dt(row["timestamp"]),
                    "desc": row.get("description", ""),
                }
            )
            # rowcount is 0 when ON CONFLICT skipped a duplicate transaction_id.
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            skipped += 1
            logger.warning("Skipping statement row %d: %s", i, e)

    await session.commit()
    return UploadResponse(message="Statement uploaded successfully", rows_inserted=inserted, rows_skipped=skipped)


@router.post("/run", response_model=ReconcileRunResponse, status_code=202)
async def trigger_reconciliation(
    source: str = Query("synthetic", description="Source of data to reconcile: synthetic or uploaded"),
    session: AsyncSession = Depends(get_async_session),
):
    """Trigger a new reconciliation run.

    Idempotency note: the synthetic path relies on the UNIQUE(transaction_id,
    break_type, source) constraint + ON CONFLICT DO NOTHING, so re-runs never
    duplicate breaks or clobber manual resolutions.

    The uploaded path is different BY DESIGN: each uploaded run replaces the whole
    dataset, so we clear the previous uploaded breaks first. Without this, stale
    breaks from a prior upload would linger after a new file is uploaded. This does
    mean resolutions on old uploaded breaks are discarded — acceptable because the
    underlying uploaded data has been replaced.
    """
    job_id = uuid.uuid4()

    if source == "uploaded":
        await session.execute(
            text("DELETE FROM reconciliation_breaks WHERE source = 'uploaded'")
        )

    await session.execute(
        text("""
            INSERT INTO reconciliation_jobs (job_id, status, started_at, source)
            VALUES (:job_id, 'pending', :now, :source)
        """),
        {"job_id": job_id, "now": _utcnow(), "source": source},
    )
    await session.commit()

    reconciliation_task.apply_async(
        args=[str(job_id), source],
        task_id=str(job_id),
    )

    return ReconcileRunResponse(
        job_id=job_id,
        status="pending",
        message=f"Reconciliation job queued. Poll /reconcile/status/{job_id} for updates.",
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get the current status of a reconciliation job."""
    result = await session.execute(
        text("""
            SELECT job_id, status, started_at, finished_at,
                   error_message, transactions_processed, breaks_detected
            FROM reconciliation_jobs
            WHERE job_id = :job_id
        """),
        {"job_id": job_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=row["job_id"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_message=row["error_message"],
        transactions_processed=int(row["transactions_processed"]) if row["transactions_processed"] is not None else None,
        breaks_detected=int(row["breaks_detected"]) if row["breaks_detected"] is not None else None,
    )
