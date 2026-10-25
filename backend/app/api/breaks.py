"""Typed queries for review, global sorting, exact amounts and CSV export."""

import csv
import io
import os
import uuid
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import case, func, or_, select, update
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
    BulkReviewRequest,
    BulkReviewResponse,
    Confidence,
    ConfidenceStat,
    ReviewRequest,
    ReviewResponse,
    SortDirection,
    SortField,
    Source,
    StatsResponse,
)

router = APIRouter(tags=["breaks"], dependencies=[Depends(require_reviewer)])


def filters(source, break_type, resolved, confidence=None, q=None):
    result = [Break.source == source]
    if break_type is not None:
        result.append(Break.break_type == break_type)
    if resolved is not None:
        result.append(Break.resolved == resolved)
    if confidence is not None:
        result.append(Break.confidence == confidence)
    if q and q.strip():
        # Escape LIKE wildcards so a search for "TXN_1" means exactly that.
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        result.append(
            or_(
                *(
                    column.ilike(pattern, escape="\\")
                    for column in (
                        Break.transaction_id,
                        Break.external_transaction_id,
                        Break.description,
                    )
                )
            )
        )
    return result


# Triage order: the least certain labels need a reviewer first.
CONFIDENCE_RANK = case(
    (Break.confidence == "low", 0),
    (Break.confidence == "medium", 1),
    (Break.confidence == "high", 2),
    else_=3,
)
SearchQuery = Query(None, max_length=100, description="Match transaction IDs or evidence text")


def exposure(break_type, internal_amount, external_amount, delta_amount):
    """Money a break leaves unexplained: the difference for amount breaks,
    otherwise the gross amount that has not been confirmed on both sides."""
    if break_type in ("AMOUNT_MISMATCH", "FX_ROUNDING") and delta_amount is not None:
        return abs(delta_amount)
    amount = internal_amount if internal_amount is not None else external_amount
    return abs(amount) if amount is not None else Decimal("0")


@router.get("/breaks", response_model=BreakListResponse)
async def list_breaks(
    break_type: BreakType | None = None,
    resolved: bool | None = None,
    confidence: Confidence | None = None,
    q: str | None = SearchQuery,
    source: Source = "synthetic",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: SortField = "detected_at",
    sort_dir: SortDirection = "desc",
    session: AsyncSession = Depends(get_async_session),
):
    conditions = filters(source, break_type, resolved, confidence, q)
    total = await session.scalar(select(func.count()).select_from(Break).where(*conditions))
    column = CONFIDENCE_RANK if sort_by == "confidence" else getattr(Break, sort_by)
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
    "confidence",
    "related_ids",
]


def csv_cell(value):
    if isinstance(value, list):
        value = " ".join(value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value.isoformat() if hasattr(value, "isoformat") else value


@router.get("/breaks/export")
async def export_breaks(
    break_type: BreakType | None = None,
    resolved: bool | None = None,
    confidence: Confidence | None = None,
    q: str | None = SearchQuery,
    source: Source = "synthetic",
    session: AsyncSession = Depends(get_async_session),
):
    records = await session.scalars(
        select(Break)
        .where(*filters(source, break_type, resolved, confidence, q))
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


@router.post("/breaks/bulk-review", response_model=BulkReviewResponse)
async def bulk_review(
    request: BulkReviewRequest,
    reviewer: str = Depends(require_reviewer),
    session: AsyncSession = Depends(get_async_session),
):
    """Resolve or reopen up to 500 breaks with one note, atomically.

    Uses the same conditional write as a single review, so breaks already in the
    requested state are left alone and get no event.
    """
    resolve = request.action == "resolve"
    values = (
        {"resolved": True, "resolved_at": utcnow(), "resolved_by": reviewer}
        if resolve
        else {"resolved": False, "resolved_at": None, "resolved_by": None}
    )
    ids = list(dict.fromkeys(request.break_ids))
    changed = (
        await session.execute(
            update(Break)
            .where(Break.break_id.in_(ids), Break.resolved.is_(not resolve))
            .values(**values)
            .returning(Break.break_id, Break.source, Break.transaction_id, Break.break_type)
        )
    ).all()
    note = (request.note or "").strip() or None
    now = utcnow()
    for row in changed:
        session.add(
            BreakEvent(
                event_id=uuid.uuid4(),
                break_id=row.break_id,
                source=row.source,
                transaction_id=row.transaction_id,
                break_type=row.break_type,
                action="resolved" if resolve else "reopened",
                reviewer=reviewer,
                note=note,
                created_at=now,
            )
        )
    await session.commit()
    verb = "resolved" if resolve else "reopened"
    return BulkReviewResponse(
        changed=len(changed),
        unchanged=len(ids) - len(changed),
        message=f"{len(changed)} break{'s' if len(changed) != 1 else ''} {verb}",
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
    open_rows = (
        await session.execute(
            select(
                Break.break_type,
                Break.confidence,
                Break.internal_amount,
                Break.external_amount,
                Break.delta_amount,
            ).where(Break.source == source, Break.resolved.is_(False))
        )
    ).all()
    open_value_by_type: dict[str, Decimal] = {}
    open_by_confidence: dict[str, int] = {}
    for row in open_rows:
        value = exposure(row.break_type, row.internal_amount, row.external_amount, row.delta_amount)
        open_value_by_type[row.break_type] = open_value_by_type.get(row.break_type, 0) + value
        level = row.confidence or "unrated"
        open_by_confidence[level] = open_by_confidence.get(level, 0) + 1
    types = [
        BreakTypeStat(
            break_type=row.break_type,
            count=row.count,
            resolved_count=row.resolved_count,
            open_value=open_value_by_type.get(row.break_type, Decimal("0")),
        )
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
        open_value=sum(open_value_by_type.values(), Decimal("0")),
        open_by_confidence=[
            ConfidenceStat(confidence=level, open_count=open_by_confidence[level])
            for level in ("low", "medium", "high", "unrated")
            if level in open_by_confidence
        ],
        ai_enabled=bool(os.getenv("GEMINI_API_KEY", "").strip()),
    )
