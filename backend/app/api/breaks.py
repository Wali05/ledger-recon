"""Typed queries for review, global sorting, exact amounts and CSV export."""

import csv
import io
import os
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_reviewer
from app.database import get_async_session
from app.models import BreakEvent, DatasetState, utcnow
from app.models import ReconciliationBreak as Break
from app.schemas import (
    BreakEventResponse,
    BreakListResponse,
    BreakResponse,
    BreakType,
    BreakTypeStat,
    ReviewRequest,
    ReviewResponse,
    SortDirection,
    SortField,
    Source,
    StatsResponse,
)

router = APIRouter(tags=["breaks"], dependencies=[Depends(require_reviewer)])


def filters(source, break_type, resolved):
    result = [Break.source == source]
    if break_type is not None:
        result.append(Break.break_type == break_type)
    if resolved is not None:
        result.append(Break.resolved == resolved)
    return result


@router.get("/breaks", response_model=BreakListResponse)
async def list_breaks(
    break_type: BreakType | None = None,
    resolved: bool | None = None,
    source: Source = "synthetic",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: SortField = "detected_at",
    sort_dir: SortDirection = "desc",
    session: AsyncSession = Depends(get_async_session),
):
    conditions = filters(source, break_type, resolved)
    total = await session.scalar(select(func.count()).select_from(Break).where(*conditions))
    column = getattr(Break, sort_by)
    order = column.asc().nullslast() if sort_dir == "asc" else column.desc().nullslast()
    items = list(
        await session.scalars(
            select(Break)
            .where(*conditions)
            .order_by(order, Break.break_id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return BreakListResponse(total=total, page=page, page_size=page_size, items=items)


EXPORT_FIELDS = [
    "break_id",
    "transaction_id",
    "external_transaction_id",
    "break_type",
    "currency",
    "internal_amount",
    "external_amount",
    "delta_amount",
    "internal_timestamp",
    "external_timestamp",
    "description",
    "detected_at",
    "resolved",
    "resolved_at",
    "resolved_by",
    "source",
    "evidence_side",
    "occurrence",
]


def csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("/breaks/export")
async def export_breaks(
    break_type: BreakType | None = None,
    resolved: bool | None = None,
    source: Source = "synthetic",
    session: AsyncSession = Depends(get_async_session),
):
    records = await session.scalars(
        select(Break)
        .where(*filters(source, break_type, resolved))
        .order_by(Break.detected_at.desc(), Break.break_id.asc())
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for record in records:
        writer.writerow({field: csv_cell(getattr(record, field)) for field in EXPORT_FIELDS})
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="breaks_{source}.csv"'},
    )


async def require_break(session, break_id):
    record = await session.get(Break, break_id)
    if not record:
        raise HTTPException(404, "Break not found")
    return record


@router.get("/breaks/{break_id}", response_model=BreakResponse)
async def get_break(break_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    return await require_break(session, break_id)


async def _review(session, break_id, *, resolve, reviewer, note):
    """Change review state with a conditional write and log it in one transaction.

    Repeating the same action is a no-op: the first timestamp, reviewer and
    event stand, so double clicks and concurrent reviewers cannot rewrite history.
    """
    record = await require_break(session, break_id)
    values = (
        {"resolved": True, "resolved_at": utcnow(), "resolved_by": reviewer}
        if resolve
        else {"resolved": False, "resolved_at": None, "resolved_by": None}
    )
    result = await session.execute(
        update(Break)
        .where(Break.break_id == break_id, Break.resolved.is_(not resolve))
        .values(**values)
    )
    changed = bool(result.rowcount)
    if changed:
        session.add(
            BreakEvent(
                event_id=uuid.uuid4(),
                break_id=break_id,
                source=record.source,
                transaction_id=record.transaction_id,
                break_type=record.break_type,
                action="resolved" if resolve else "reopened",
                reviewer=reviewer,
                note=(note or "").strip() or None,
                created_at=utcnow(),
            )
        )
    await session.commit()
    record = await session.get(Break, break_id, populate_existing=True)
    verb = "resolved" if resolve else "reopened"
    return ReviewResponse(
        break_id=break_id,
        resolved=record.resolved,
        resolved_at=record.resolved_at,
        resolved_by=record.resolved_by,
        message=f"Break {verb}" if changed else f"Break was already {verb}",
    )


@router.post("/breaks/{break_id}/resolve", response_model=ReviewResponse)
async def resolve_break(
    break_id: uuid.UUID,
    review: ReviewRequest | None = Body(default=None),
    reviewer: str = Depends(require_reviewer),
    session: AsyncSession = Depends(get_async_session),
):
    note = review.note if review else None
    return await _review(session, break_id, resolve=True, reviewer=reviewer, note=note)


@router.post("/breaks/{break_id}/reopen", response_model=ReviewResponse)
async def reopen_break(
    break_id: uuid.UUID,
    review: ReviewRequest | None = Body(default=None),
    reviewer: str = Depends(require_reviewer),
    session: AsyncSession = Depends(get_async_session),
):
    note = review.note if review else None
    return await _review(session, break_id, resolve=False, reviewer=reviewer, note=note)


@router.get("/breaks/{break_id}/events", response_model=list[BreakEventResponse])
async def break_events(break_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    return list(
        await session.scalars(
            select(BreakEvent)
            .where(BreakEvent.break_id == break_id)
            .order_by(BreakEvent.created_at, BreakEvent.event_id)
        )
    )


@router.get("/audit", response_model=list[BreakEventResponse])
async def audit_log(
    source: Source = "synthetic",
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_async_session),
):
    """Most recent review events, including those for replaced uploads."""
    return list(
        await session.scalars(
            select(BreakEvent)
            .where(BreakEvent.source == source)
            .order_by(BreakEvent.created_at.desc(), BreakEvent.event_id.desc())
            .limit(limit)
        )
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    source: Source = "synthetic", session: AsyncSession = Depends(get_async_session)
):
    state = await session.get(DatasetState, source)
    groups = (
        await session.execute(
            select(
                Break.break_type,
                func.count().label("count"),
                func.sum(case((Break.resolved.is_(True), 1), else_=0)).label("resolved_count"),
            )
            .where(Break.source == source)
            .group_by(Break.break_type)
            .order_by(Break.break_type)
        )
    ).all()
    types = [
        BreakTypeStat(break_type=row.break_type, count=row.count, resolved_count=row.resolved_count)
        for row in groups
    ]
    total = sum(row.count for row in types)
    resolved = sum(row.resolved_count for row in types)
    return StatsResponse(
        total_transactions_in_ledger=state.ledger_rows,
        total_transactions_in_statement=state.statement_rows,
        total_breaks_detected=total,
        total_breaks_resolved=resolved,
        resolution_rate_pct=round(100 * resolved / total, 2) if total else 0,
        breaks_by_type=types,
        ai_enabled=bool(os.getenv("GEMINI_API_KEY", "").strip()),
    )
