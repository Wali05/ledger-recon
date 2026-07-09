"""
FastAPI application entry point.

Creates all DB tables on startup, mounts routers, and configures CORS
to allow the React dev server (localhost:5173) to call this API.
"""

import os
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

# CORS is restricted to an explicit allow-list of origins.
#
# NOTE: production traffic goes through the Vercel `/api/*` rewrite, which proxies
# to this backend server-side — those requests are same-origin and never trigger
# CORS. This allow-list therefore only matters for direct/browser calls (local dev,
# or anything hitting the DigitalOcean host directly).
#
# Set ALLOWED_ORIGINS in the environment as a comma-separated list, e.g.
#   ALLOWED_ORIGINS=https://your-app.vercel.app,http://localhost:5173
# Falls back to the local dev origins if unset.
#
# allow_credentials is False: the frontend uses plain fetch with no cookies/auth
# headers, so credentials aren't needed — and "*" + credentials is invalid per the
# CORS spec anyway.
_origins_env = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reconcile_router)
app.include_router(breaks_router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "ledger-reconciliation-engine"}
