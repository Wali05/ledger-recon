"""One database URL, synchronous workers and asynchronous HTTP sessions."""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "ledger_recon.db"


def database_urls(value: str):
    value = value.strip() or f"sqlite:///{DEFAULT_PATH.as_posix()}"
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]
    url = make_url(value)
    backend = url.get_backend_name()
    if backend == "sqlite":
        return url.set(drivername="sqlite+aiosqlite"), url.set(drivername="sqlite")
    if backend == "postgresql":
        return url.set(drivername="postgresql+asyncpg"), url.set(drivername="postgresql+psycopg2")
    raise ValueError("DATABASE_URL must use SQLite or PostgreSQL")


ASYNC_DATABASE_URL, SYNC_DATABASE_URL = database_urls(os.getenv("DATABASE_URL", ""))
IS_SQLITE = SYNC_DATABASE_URL.get_backend_name() == "sqlite"
DATABASE_URL = SYNC_DATABASE_URL
async_engine = create_async_engine(ASYNC_DATABASE_URL, pool_pre_ping=True)
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30} if IS_SQLITE else {},
)


def _sqlite_connection(connection, _):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


if IS_SQLITE:
    event.listen(sync_engine, "connect", _sqlite_connection)
    event.listen(async_engine.sync_engine, "connect", _sqlite_connection)

AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session
