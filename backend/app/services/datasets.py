"""A database row lock coordinates uploads, admission and worker publication."""

import hashlib

from fastapi import HTTPException
from sqlalchemy import delete, insert, select, update

from app.models import DatasetState, ReconciliationBreak, ReconciliationJob


async def lock_dataset(session, source):
    # UPDATE acquires a write lock on both supported backends (SQLite ignores FOR UPDATE).
    await session.execute(
        update(DatasetState)
        .where(DatasetState.source == source)
        .values(ledger_rows=DatasetState.ledger_rows)
    )
    return await session.get(DatasetState, source, populate_existing=True)


async def ensure_idle(session, source):
    active = await session.scalar(
        select(ReconciliationJob.job_id).where(
            ReconciliationJob.source == source,
            ReconciliationJob.status.in_(["pending", "running"]),
        )
    )
    if active:
        raise HTTPException(409, "A reconciliation for this dataset is already queued or running")


async def replace_feeds(session, feeds):
    state = await lock_dataset(session, "uploaded")
    await ensure_idle(session, "uploaded")
    changed = False
    for name, model, content, rows in feeds:
        fingerprint = hashlib.sha256(content).hexdigest()
        if getattr(state, f"{name}_hash") == fingerprint:
            continue
        await session.execute(delete(model))
        await session.execute(insert(model), rows)
        setattr(state, f"{name}_hash", fingerprint)
        setattr(state, f"{name}_rows", len(rows))
        changed = True
    if changed:
        await session.execute(
            delete(ReconciliationBreak).where(ReconciliationBreak.source == "uploaded")
        )
        await session.execute(
            delete(ReconciliationJob).where(ReconciliationJob.source == "uploaded")
        )
    await session.commit()
    return state, changed
