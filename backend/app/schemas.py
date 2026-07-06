"""Pydantic v2 request/response schemas."""

from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ─── Break Types ────────────────────────────────────────────────────────────

BREAK_TYPES = [
    "AMOUNT_MISMATCH",
    "MISSING_INTERNAL",
    "MISSING_EXTERNAL",
    "DUPLICATE",
    "TIMING_LAG",
    "FX_ROUNDING",
    "UNKNOWN",
]


# ─── Reconciliation Job ──────────────────────────────────────────────────────

class ReconcileRunResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: UUID
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    transactions_processed: Optional[int] = None
    breaks_detected: Optional[int] = None


# ─── Breaks ─────────────────────────────────────────────────────────────────

class BreakResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    break_id: UUID
    transaction_id: str
    break_type: str
    internal_amount: Optional[Decimal] = None
    external_amount: Optional[Decimal] = None
    delta_amount: Optional[Decimal] = None
    internal_timestamp: Optional[datetime] = None
    external_timestamp: Optional[datetime] = None
    description: Optional[str] = None
    detected_at: datetime
    resolved: bool
    resolved_at: Optional[datetime] = None
    job_id: Optional[UUID] = None
    source: str = "synthetic"
    ai_explanation: Optional[str] = None


class UploadResponse(BaseModel):
    message: str
    rows_inserted: int
    rows_skipped: int


class BreakListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[BreakResponse]


class ResolveBreakResponse(BaseModel):
    break_id: UUID
    resolved: bool
    resolved_at: datetime
    message: str


# ─── Stats ───────────────────────────────────────────────────────────────────

class BreakTypeStat(BaseModel):
    break_type: str
    count: int
    resolved_count: int


class StatsResponse(BaseModel):
    total_transactions_in_ledger: int
    total_breaks_detected: int
    total_breaks_resolved: int
    resolution_rate_pct: float
    breaks_by_type: List[BreakTypeStat]
