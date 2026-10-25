"""Typed HTTP contracts shared by validation and OpenAPI."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Source = Literal["synthetic", "uploaded"]
BreakType = Literal[
    "AMOUNT_MISMATCH",
    "MISSING_INTERNAL",
    "MISSING_EXTERNAL",
    "DUPLICATE",
    "TIMING_LAG",
    "FX_ROUNDING",
    "REFERENCE_MISMATCH",
    "SPLIT_SETTLEMENT",
    "UNKNOWN",
]
Confidence = Literal["high", "medium", "low"]
SortField = Literal[
    "transaction_id",
    "break_type",
    "internal_amount",
    "external_amount",
    "delta_amount",
    "detected_at",
    "resolved",
    "confidence",
]
SortDirection = Literal["asc", "desc"]


class ReconcileRunResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: UUID
    source: Source
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    transactions_processed: int | None = None
    breaks_detected: int | None = None
    breaks_inserted: int | None = None
    breaks_retired: int | None = None


class BreakResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    break_id: UUID
    transaction_id: str
    external_transaction_id: str | None = None
    break_type: str
    currency: str | None = None
    evidence_side: str
    occurrence: int
    internal_amount: Decimal | None = None
    external_amount: Decimal | None = None
    delta_amount: Decimal | None = None
    internal_timestamp: datetime | None = None
    external_timestamp: datetime | None = None
    description: str | None = None
    detected_at: datetime
    resolved: bool
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    job_id: UUID | None = None
    source: Source
    ai_explanation: str | None = None
    confidence: Confidence | None = None
    related_ids: list[str] | None = None


class UploadResponse(BaseModel):
    message: str
    rows_inserted: int
    rows_skipped: int = 0


class PairUploadResponse(BaseModel):
    message: str
    ledger_rows: int
    statement_rows: int
    replaced: bool


class BreakListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[BreakResponse]


class ReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class BulkReviewRequest(BaseModel):
    action: Literal["resolve", "reopen"]
    break_ids: list[UUID] = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class BulkReviewResponse(BaseModel):
    changed: int
    unchanged: int
    message: str


class ReviewResponse(BaseModel):
    break_id: UUID
    resolved: bool
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    message: str


class BreakEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: UUID
    break_id: UUID
    source: Source
    transaction_id: str
    break_type: str
    action: Literal["resolved", "reopened"]
    reviewer: str
    note: str | None = None
    created_at: datetime


class SessionResponse(BaseModel):
    auth_required: bool
    reviewer: str | None = None


class BreakTypeStat(BaseModel):
    break_type: str
    count: int
    resolved_count: int
    open_value: Decimal = Decimal("0")


class ConfidenceStat(BaseModel):
    confidence: str
    open_count: int


class StatsResponse(BaseModel):
    total_transactions_in_ledger: int
    total_transactions_in_statement: int
    total_breaks_detected: int
    total_breaks_resolved: int
    resolution_rate_pct: float
    breaks_by_type: list[BreakTypeStat]
    open_value: Decimal = Decimal("0")
    open_by_confidence: list[ConfidenceStat] = []
    ai_enabled: bool
