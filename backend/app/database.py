"""
Database engine and session factory.

PORTABILITY DESIGN — why this module looks the way it does:

  This app needs TWO engines from ONE connection string:
    - an async engine (asyncpg / aiosqlite) for the FastAPI request path
    - a sync engine  (psycopg2 / sqlite3)   for Celery workers, which run
      in a plain synchronous process

  An earlier version required the operator to supply BOTH urls by hand
  (DATABASE_URL *and* SYNC_DATABASE_URL). That made the app deployable to
  exactly one place: a VPS where you hand-edit an .env file. Every managed
  platform (Render, Railway, Fly, Neon, Supabase, Heroku) injects a single
  DATABASE_URL, and most still emit the legacy "postgres://" scheme that
  SQLAlchemy 2.x refuses to parse.

  So: we take one url, normalise it, and derive both drivers from it.

ZERO-INFRASTRUCTURE DEFAULT:
  If DATABASE_URL is unset we fall back to a local SQLite file. That means
  `pip install -r requirements.txt` followed by `uvicorn app.main:app` is
  enough to run the whole project — no Postgres, no Docker, no cloud account.
  Postgres remains the production target (see docker-compose.yml); SQLite is
  the "clone it and see it work in 60 seconds" path.
"""

import os
import sqlite3
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ── Where SQLite lives when no DATABASE_URL is supplied ──────────────────────
# backend/ledger_recon.db — sibling of the app package, gitignored.
_DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "ledger_recon.db"


def _normalise(url: str) -> str:
    """
    Fix up the scheme quirks that managed Postgres providers emit.

    - "postgres://"    -> "postgresql://"   (SQLAlchemy 2.x dropped the alias)
    - strips any driver already pinned by the provider, so we can pick our own
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Some providers hand out "postgresql+psycopg2://" — drop the driver so the
    # async/sync helpers below can each attach the driver they actually need.
    if url.startswith("postgresql+"):
        url = "postgresql://" + url.split("://", 1)[1]
    return url


def _async_url(url: str) -> str:
    """Attach the async driver appropriate to the backend."""
    if url.startswith("sqlite"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _sync_url(url: str) -> str:
    """Attach the sync driver appropriate to the backend."""
    if url.startswith("sqlite"):
        return url
    return url  # psycopg2 is SQLAlchemy's default driver for postgresql://


_raw_url = os.getenv("DATABASE_URL", "").strip()
if not _raw_url:
    _raw_url = f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"

DATABASE_URL = _normalise(_raw_url)
ASYNC_DATABASE_URL = _async_url(DATABASE_URL)
SYNC_DATABASE_URL = _sync_url(DATABASE_URL)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# ── sqlite3 cannot bind a uuid.UUID parameter ────────────────────────────────
# Most of this app's queries are raw text() SQL, which bypasses SQLAlchemy's
# type system for bound parameters — so a uuid.UUID passed as a param reaches
# the DBAPI untouched. Postgres drivers handle that; sqlite3 raises
# "InterfaceError: Error binding parameter". Registering an adapter once here
# lets the same query strings run unchanged against both databases.
sqlite3.register_adapter(uuid.UUID, str)

# SQLite needs check_same_thread=False because Celery/uvicorn hand connections
# between threads. Postgres pooling options don't apply to a file-backed DB.
_async_kwargs: dict = {"echo": False}
_sync_kwargs: dict = {"echo": False}
if IS_SQLITE:
    _sync_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _async_kwargs["pool_pre_ping"] = True
    _sync_kwargs["pool_pre_ping"] = True

async_engine = create_async_engine(ASYNC_DATABASE_URL, **_async_kwargs)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

sync_engine = create_engine(SYNC_DATABASE_URL, **_sync_kwargs)
SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


async def get_async_session():
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session():
    """Celery task dependency: yields a synchronous DB session."""
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()
