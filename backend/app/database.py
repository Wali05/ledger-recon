"""
Database engine and session factory.

Uses SQLAlchemy 2.0 async engine (asyncpg driver) for the FastAPI layer,
and a separate sync engine for Celery tasks (which run in a synchronous context).
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Async engine — used by FastAPI endpoints
ASYNC_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://recon_user:recon_pass@localhost:5432/ledger_recon",
)

# Sync engine — used by Celery tasks (Celery workers are synchronous)
SYNC_DATABASE_URL = os.getenv(
    "SYNC_DATABASE_URL",
    "postgresql://recon_user:recon_pass@localhost:5432/ledger_recon",
)

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

sync_engine = create_engine(SYNC_DATABASE_URL, echo=False, pool_pre_ping=True)
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
