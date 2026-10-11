"""Application startup, migration and local recovery of interrupted jobs."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, update
from starlette.concurrency import run_in_threadpool

from app.api.breaks import router as breaks_router
from app.api.explanations import router as explanations_router
from app.api.reconcile import router as reconcile_router
from app.auth import auth_required, load_keys, require_reviewer
from app.celery_app import EAGER_MODE
from app.database import AsyncSessionLocal, async_engine
from app.engine.matcher import load_external_statement, load_internal_ledger
from app.migrate import migrate
from app.models import DatasetState, ReconciliationJob, utcnow
from app.schemas import SessionResponse
from app.tasks import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app):
    load_keys()  # Fail fast on a malformed API_KEYS value.
    if os.getenv("AUTO_MIGRATE", "true").lower() == "true":
        await run_in_threadpool(migrate)
    internal = await run_in_threadpool(load_internal_ledger, DATA_DIR / "internal_ledger.csv")
    external = await run_in_threadpool(load_external_statement, DATA_DIR / "bank_statement.csv")
    async with AsyncSessionLocal() as session:
        state = await session.get(DatasetState, "synthetic")
        if state is None:
            raise RuntimeError("Database schema is missing. Run python -m app.migrate first.")
        state.ledger_rows, state.statement_rows = len(internal), len(external)
        if EAGER_MODE:
            # Local background work is not durable across process restarts.
            # Local mode supports one API process; Redis workers are separate.
            await session.execute(
                update(ReconciliationJob)
                .where(ReconciliationJob.status.in_(["pending", "running"]))
                .values(
                    status="failed",
                    finished_at=utcnow(),
                    error_message="Local API restarted before the job finished. Run it again.",
                )
            )
        await session.commit()
    yield
    await async_engine.dispose()


app = FastAPI(
    title="Ledger Recon",
    version="2.0.0",
    description="Compare ledger and statement feeds, review discrepancies, and preserve resolutions across unchanged reruns.",
    lifespan=lifespan,
)
origins = [value.strip() for value in os.getenv("ALLOWED_ORIGINS", "").split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(reconcile_router)
app.include_router(breaks_router)
app.include_router(explanations_router)


@app.get("/session", response_model=SessionResponse, tags=["auth"])
async def session_info(authorization: str | None = Header(default=None)):
    """Public: tells the dashboard whether to ask for an API key, and whose it is."""
    try:
        reviewer = await require_reviewer(authorization)
    except HTTPException:
        reviewer = None
    return SessionResponse(auth_required=auth_required(), reviewer=reviewer)


@app.get("/health", tags=["health"])
async def health():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc
    return {"status": "ok", "service": "ledger-recon", "mode": "local" if EAGER_MODE else "worker"}
