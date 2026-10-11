"""Validate uploads, admit one job per dataset, and expose durable job state."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.celery_app import EAGER_MODE
from app.database import get_async_session
from app.models import (
    ReconciliationJob,
    UploadedLedgerTransaction,
    UploadedStatementTransaction,
    utcnow,
)
from app.schemas import (
    JobStatusResponse,
    PairUploadResponse,
    ReconcileRunResponse,
    Source,
    UploadResponse,
)
from app.services.csv_import import MAX_BYTES, CSVValidationError, parse_csv
from app.services.datasets import ensure_idle, lock_dataset, replace_feeds
from app.tasks import reconciliation_task

router = APIRouter(prefix="/reconcile", tags=["reconciliation"])
logger = logging.getLogger(__name__)


async def _read(file, ledger):
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "File exceeds the 10 MiB limit")
    try:
        return content, parse_csv(content, ledger=ledger)
    except CSVValidationError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/upload", response_model=PairUploadResponse)
async def upload_pair(
    ledger: UploadFile = File(...),
    statement: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
):
    ledger_content, ledger_rows = await _read(ledger, True)
    statement_content, statement_rows = await _read(statement, False)
    state, changed = await replace_feeds(
        session,
        [
            ("ledger", UploadedLedgerTransaction, ledger_content, ledger_rows),
            ("statement", UploadedStatementTransaction, statement_content, statement_rows),
        ],
    )
    return PairUploadResponse(
        message="Dataset replaced"
        if changed
        else "Identical files; existing results and resolutions retained",
        ledger_rows=state.ledger_rows,
        statement_rows=state.statement_rows,
        replaced=changed,
    )


@router.post("/upload/ledger", response_model=UploadResponse)
async def upload_ledger(
    file: UploadFile = File(...), session: AsyncSession = Depends(get_async_session)
):
    content, rows = await _read(file, True)
    _, changed = await replace_feeds(
        session, [("ledger", UploadedLedgerTransaction, content, rows)]
    )
    return UploadResponse(
        message="Ledger replaced" if changed else "Identical ledger retained",
        rows_inserted=len(rows),
    )


@router.post("/upload/statement", response_model=UploadResponse)
async def upload_statement(
    file: UploadFile = File(...), session: AsyncSession = Depends(get_async_session)
):
    content, rows = await _read(file, False)
    _, changed = await replace_feeds(
        session, [("statement", UploadedStatementTransaction, content, rows)]
    )
    return UploadResponse(
        message="Statement replaced" if changed else "Identical statement retained",
        rows_inserted=len(rows),
    )


def _run_local(job_id, source):
    # A synchronous BackgroundTask is placed in Starlette's thread pool.
    # Celery .apply executes the same task body without contacting a broker.
    reconciliation_task.apply(args=[job_id, source], throw=False)


@router.post("/run", response_model=ReconcileRunResponse, status_code=202)
async def trigger_reconciliation(
    background_tasks: BackgroundTasks,
    source: Source = Query("synthetic"),
    session: AsyncSession = Depends(get_async_session),
):
    state = await lock_dataset(session, source)
    await ensure_idle(session, source)
    if not state.ledger_rows or not state.statement_rows:
        raise HTTPException(409, "Upload both a ledger and a statement before reconciling")
    job = ReconciliationJob(job_id=uuid.uuid4(), source=source, status="pending")
    session.add(job)
    await session.commit()
    if EAGER_MODE:
        background_tasks.add_task(_run_local, str(job.job_id), source)
    else:
        try:
            await run_in_threadpool(
                reconciliation_task.apply_async,
                args=[str(job.job_id), source],
                task_id=str(job.job_id),
                retry=False,
            )
        except Exception as exc:
            logger.exception("Could not dispatch reconciliation job")
            await session.execute(
                update(ReconciliationJob)
                .where(ReconciliationJob.job_id == job.job_id)
                .values(status="failed", finished_at=utcnow(), error_message="Queue unavailable")
            )
            await session.commit()
            raise HTTPException(
                503, "Reconciliation queue is unavailable. Try again later."
            ) from exc
    return ReconcileRunResponse(
        job_id=job.job_id,
        status="pending",
        message=f"Job accepted. Poll /reconcile/status/{job.job_id} for updates.",
    )


@router.get("/jobs", response_model=list[JobStatusResponse])
async def list_jobs(
    source: Source = Query("synthetic"), session: AsyncSession = Depends(get_async_session)
):
    return list(
        await session.scalars(
            select(ReconciliationJob)
            .where(ReconciliationJob.source == source)
            .order_by(
                case((ReconciliationJob.status.in_(["pending", "running"]), 0), else_=1),
                ReconciliationJob.started_at.desc().nullslast(),
                ReconciliationJob.job_id.desc(),
            )
            .limit(10)
        )
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    job = await session.get(ReconciliationJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job
