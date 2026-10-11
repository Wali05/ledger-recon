"""Exercise the actual app with an isolated database, never a developer's data."""

import os
import tempfile
from pathlib import Path

import pytest

_directory = tempfile.TemporaryDirectory(prefix="ledger-recon-tests-")
os.environ["DATABASE_URL"] = (
    os.getenv("TEST_DATABASE_URL") or "sqlite:///" + Path(_directory.name, "test.db").as_posix()
)
for name in ("CELERY_BROKER_URL", "REDIS_URL", "GEMINI_API_KEY"):
    os.environ.pop(name, None)

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import SyncSessionLocal, sync_engine
from app.main import app
from app.migrate import migrate
from app.models import Base, DatasetState


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    migrate()
    with SyncSessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "dataset_state":
                session.execute(delete(table))
        state = session.get(DatasetState, "uploaded")
        state.ledger_hash = state.statement_hash = None
        state.ledger_rows = state.statement_rows = 0
        session.commit()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def close_engines():
    yield
    sync_engine.dispose()
    _directory.cleanup()
