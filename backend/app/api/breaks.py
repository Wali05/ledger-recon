"""
Break management endpoints.

GET  /breaks                    — list all breaks (filterable, paginated)
GET  /breaks/{break_id}         — detail view
POST /breaks/{break_id}/resolve — mark as manually resolved
GET  /stats                     — aggregate summary stats
"""

import csv
import io
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis
from google import genai

from app.database import get_async_session
from app.schemas import (
    BreakResponse, BreakListResponse, ResolveBreakResponse,
    StatsResponse, BreakTypeStat,
)

router = APIRouter(tags=["breaks"])


def _utcnow():
    return datetime.now(timezone.utc)


def _row_to_break(row) -> BreakResponse:
    return BreakResponse(
        break_id=row["break_id"],
        transaction_id=row["transaction_id"],
        break_type=row["break_type"],
        internal_amount=row["internal_amount"],
        external_amount=row["external_amount"],
        delta_amount=row["delta_amount"],
        internal_timestamp=row["internal_timestamp"],
        external_timestamp=row["external_timestamp"],
        description=row["description"],
        detected_at=row["detected_at"],
        resolved=row["resolved"],
        resolved_at=row["resolved_at"],
        job_id=row["job_id"],
    )


@router.get("/breaks", response_model=BreakListResponse)
async def list_breaks(
    break_type: Optional[str] = Query(None, description="Filter by break type"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    source: str = Query("synthetic", description="Filter by source (synthetic or uploaded)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all detected breaks with optional filtering.

    Supports filtering by break_type (AMOUNT_MISMATCH, MISSING_INTERNAL, etc.)
    and resolved status. Paginated.
    """
    # Build dynamic WHERE clauses
    conditions = ["source = :source"]
    params: dict = {"source": source}
    if break_type is not None:
        conditions.append("break_type = :break_type")
        params["break_type"] = break_type
    if resolved is not None:
        conditions.append("resolved = :resolved")
        params["resolved"] = resolved

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size

    count_result = await session.execute(
        text(f"SELECT COUNT(*) FROM reconciliation_breaks {where}"),
        params,
    )
    total = count_result.scalar_one()

    params["limit"] = page_size
    params["offset"] = offset
    rows_result = await session.execute(
        text(f"""
            SELECT break_id, transaction_id, break_type, internal_amount,
                   external_amount, delta_amount, internal_timestamp,
                   external_timestamp, description, detected_at, resolved,
                   resolved_at, job_id
            FROM reconciliation_breaks
            {where}
            ORDER BY detected_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = rows_result.mappings().all()

    return BreakListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_row_to_break(r) for r in rows],
    )


@router.get("/breaks/export")
async def export_breaks(
    break_type: Optional[str] = Query(None, description="Filter by break type"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    source: str = Query("synthetic", description="Filter by source (synthetic or uploaded)"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Export breaks to CSV format based on the current filters.
    """
    conditions = ["source = :source"]
    params: dict = {"source": source}
    if break_type is not None:
        conditions.append("break_type = :break_type")
        params["break_type"] = break_type
    if resolved is not None:
        conditions.append("resolved = :resolved")
        params["resolved"] = resolved

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows_result = await session.execute(
        text(f"""
            SELECT break_id, transaction_id, break_type, internal_amount,
                   external_amount, delta_amount, internal_timestamp,
                   external_timestamp, description, detected_at, resolved,
                   resolved_at, ai_explanation
            FROM reconciliation_breaks
            {where}
            ORDER BY detected_at DESC
        """),
        params,
    )
    rows = rows_result.mappings().all()

    output = io.StringIO()
    if not rows:
        return Response(content="", media_type="text/csv")
    
    # We want to output all columns returned by the query
    fieldnames = list(rows[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))

    csv_content = output.getvalue()
    
    timestamp = _utcnow().strftime("%Y%m%d_%H%M%S")
    headers = {
        "Content-Disposition": f"attachment; filename=breaks_export_{timestamp}.csv"
    }

    return Response(content=csv_content, media_type="text/csv", headers=headers)


@router.get("/breaks/{break_id}", response_model=BreakResponse)
async def get_break(
    break_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get full detail for a single break."""
    result = await session.execute(
        text("""
            SELECT break_id, transaction_id, break_type, internal_amount,
                   external_amount, delta_amount, internal_timestamp,
                   external_timestamp, description, detected_at, resolved,
                   resolved_at, job_id
            FROM reconciliation_breaks
            WHERE break_id = :break_id
        """),
        {"break_id": break_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Break {break_id} not found")
    return _row_to_break(row)


@router.post("/breaks/{break_id}/resolve", response_model=ResolveBreakResponse)
async def resolve_break(
    break_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Mark a break as manually resolved.

    This is idempotent: resolving an already-resolved break is a no-op that
    returns the existing resolved_at timestamp. The resolved flag is never
    cleared by a re-run of the reconciliation job — only by a future human action.
    """
    # Check existence
    result = await session.execute(
        text("SELECT break_id, resolved, resolved_at FROM reconciliation_breaks WHERE break_id = :bid"),
        {"bid": break_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Break {break_id} not found")

    if row["resolved"]:
        return ResolveBreakResponse(
            break_id=break_id,
            resolved=True,
            resolved_at=row["resolved_at"],
            message="Break was already resolved.",
        )

    now = _utcnow()
    await session.execute(
        text("""
            UPDATE reconciliation_breaks
            SET resolved = true, resolved_at = :now
            WHERE break_id = :bid
        """),
        {"now": now, "bid": break_id},
    )
    await session.commit()

    return ResolveBreakResponse(
        break_id=break_id,
        resolved=True,
        resolved_at=now,
        message="Break marked as resolved.",
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    source: str = Query("synthetic", description="Filter by source"),
    session: AsyncSession = Depends(get_async_session)
):
    """
    Aggregate summary statistics.

    Returns:
      - total_transactions_in_ledger: count of rows in the ledger table
      - total_breaks_detected: total break records
      - total_breaks_resolved: how many have been manually resolved
      - resolution_rate_pct: percentage of breaks that have been resolved
      - breaks_by_type: per-type counts and resolved counts
    """
    # Total ledger rows (only counting synthetic for now as requested, or we can use the uploaded table)
    if source == "uploaded":
        ledger_result = await session.execute(text("SELECT COUNT(*) FROM uploaded_ledger"))
    else:
        ledger_result = await session.execute(text("SELECT COUNT(*) FROM ledger"))
    total_ledger = ledger_result.scalar_one()

    # Break totals
    breaks_result = await session.execute(
        text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN resolved THEN 1 ELSE 0 END) as resolved_count
            FROM reconciliation_breaks
            WHERE source = :source
        """),
        {"source": source}
    )
    br = breaks_result.mappings().first()
    total_breaks = int(br["total"] or 0)
    total_resolved = int(br["resolved_count"] or 0)
    resolution_rate = (total_resolved / total_breaks * 100) if total_breaks > 0 else 0.0

    # Per-type breakdown
    type_result = await session.execute(
        text("""
            SELECT
                break_type,
                COUNT(*) as count,
                SUM(CASE WHEN resolved THEN 1 ELSE 0 END) as resolved_count
            FROM reconciliation_breaks
            WHERE source = :source
            GROUP BY break_type
            ORDER BY count DESC
        """),
        {"source": source}
    )
    breaks_by_type = [
        BreakTypeStat(
            break_type=row["break_type"],
            count=int(row["count"]),
            resolved_count=int(row["resolved_count"] or 0),
        )
        for row in type_result.mappings().all()
    ]

    return StatsResponse(
        total_transactions_in_ledger=total_ledger,
        total_breaks_detected=total_breaks,
        total_breaks_resolved=total_resolved,
        resolution_rate_pct=round(resolution_rate, 2),
        breaks_by_type=breaks_by_type,
    )


# Set up Redis client for rate limiting
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(redis_url)

@router.post("/breaks/{break_id}/ai-explain")
async def explain_break_with_ai(
    break_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Use Gemini AI to explain why a break occurred.
    Enforces strict rate limits: 15/min and 500/day.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable is not configured.")

    # 1. Check database if we already have an explanation
    result = await session.execute(
        text("""
            SELECT break_id, transaction_id, break_type, internal_amount,
                   external_amount, delta_amount, description, ai_explanation
            FROM reconciliation_breaks
            WHERE break_id = :break_id
        """),
        {"break_id": break_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Break {break_id} not found")

    if row["ai_explanation"]:
        # Cache hit!
        return {"explanation": row["ai_explanation"]}

    # 2. Rate limiting check using Redis
    now = _utcnow()
    minute_key = f"ai_rate_limit:min:{now.strftime('%Y-%m-%d:%H:%M')}"
    day_key = f"ai_rate_limit:day:{now.strftime('%Y-%m-%d')}"

    # NX ensures the TTL is only set on the first increment of each window, so the
    # expiry isn't pushed forward on every request (which would make the window slide
    # indefinitely and never reset the count).
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(minute_key)
        pipe.expire(minute_key, 60, nx=True)
        pipe.incr(day_key)
        pipe.expire(day_key, 86400, nx=True)
        res = await pipe.execute()

    min_count = res[0]
    day_count = res[2]

    if min_count > 15:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: 15 requests per minute allowed.")
    if day_count > 500:
        raise HTTPException(status_code=429, detail="Rate limit exceeded: 500 requests per day allowed.")

    # 3. Call Gemini API
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are an expert financial reconciliation assistant. 
    A reconciliation break has occurred between our internal ledger and the external bank statement.
    
    Break Details:
    - Break Type: {row['break_type']}
    - Transaction ID: {row['transaction_id']}
    - Internal Amount: {row['internal_amount']}
    - External Amount: {row['external_amount']}
    - Difference (Delta): {row['delta_amount']}
    - Ledger Description: {row['description']}
    
    Please provide a concise, human-readable explanation (2-3 sentences max) suggesting why this mismatch might have occurred and how a human operator might resolve it. Do not use formatting like markdown. Keep it direct and professional.
    """

    try:
        response = await client.aio.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt,
        )
        explanation = response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

    # 4. Save to database to cache the result
    await session.execute(
        text("""
            UPDATE reconciliation_breaks
            SET ai_explanation = :explanation
            WHERE break_id = :break_id
        """),
        {"explanation": explanation, "break_id": break_id}
    )
    await session.commit()

    return {"explanation": explanation}
