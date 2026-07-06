"""
FastAPI application entry point.

Creates all DB tables on startup, mounts routers, and configures CORS
to allow the React dev server (localhost:5173) to call this API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import async_engine, Base
from app.api.reconcile import router as reconcile_router
from app.api.breaks import router as breaks_router

# Import models so SQLAlchemy metadata is populated before create_all
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (idempotent — skips if they exist)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Ledger Reconciliation Engine",
    description=(
        "Detects discrepancies between an internal financial ledger and external "
        "bank statements. Runs reconciliation jobs asynchronously via Celery/Redis."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow React dev server and any localhost origin during development.
# In production this would be locked down to specific domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://frontend:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reconcile_router)
app.include_router(breaks_router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "ledger-reconciliation-engine"}
