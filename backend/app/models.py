"""
SQLAlchemy ORM models.

Key design decision — idempotency via DB constraint:
The reconciliation_breaks table has a UNIQUE constraint on (transaction_id, break_type).
This means if the reconciliation job runs twice on identical data, the second INSERT
will conflict and be silently ignored (ON CONFLICT DO NOTHING). This is enforced at
the DATABASE level, not just in application code, so no application bug can bypass it.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Numeric, DateTime, Boolean, ForeignKey,
    UniqueConstraint, Text, Index,
)
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class LedgerTransaction(Base):
    """
    Internal ledger — represents the bank/accounting system's record of a transaction.
    This is the authoritative source from the company's perspective.
    """
    __tablename__ = "ledger"

    transaction_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    timestamp = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="settled")


class UploadedLedgerTransaction(Base):
    """Uploaded version of the internal ledger."""
    __tablename__ = "uploaded_ledger"

    transaction_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    timestamp = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="settled")


class UploadedStatementTransaction(Base):
    """Uploaded version of the external bank statement."""
    __tablename__ = "uploaded_statement"

    transaction_id = Column(String, primary_key=True)
    amount = Column(Numeric(18, 4), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text, nullable=True)


class ReconciliationJob(Base):
    """
    Tracks the state of each reconciliation run.
    job_id is the Celery task_id, which allows direct lookups via Celery's result backend.
    """
    __tablename__ = "reconciliation_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(20), nullable=False, default="pending")  # pending/running/complete/failed
    source = Column(String(20), nullable=False, default="synthetic")  # synthetic/uploaded
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    transactions_processed = Column(Numeric, nullable=True)
    breaks_detected = Column(Numeric, nullable=True)


class ReconciliationBreak(Base):
    """
    Each row represents a detected discrepancy between the internal ledger
    and the external bank statement.

    IDEMPOTENCY CONSTRAINT:
    The UniqueConstraint on (transaction_id, break_type) is the core idempotency
    mechanism. Combined with ON CONFLICT DO NOTHING on inserts, running the same
    reconciliation job twice on unchanged data is safe — no duplicate breaks are
    created, and existing resolved breaks are NOT overwritten.

    This is deliberately a DB-level constraint (not just application logic) so that
    even direct DB writes or parallel workers cannot violate it.
    """
    __tablename__ = "reconciliation_breaks"

    break_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String, nullable=False)
    break_type = Column(String(30), nullable=False)
    internal_amount = Column(Numeric(18, 4), nullable=True)
    external_amount = Column(Numeric(18, 4), nullable=True)
    delta_amount = Column(Numeric(18, 4), nullable=True)
    internal_timestamp = Column(DateTime(timezone=True), nullable=True)
    external_timestamp = Column(DateTime(timezone=True), nullable=True)
    description = Column(Text, nullable=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("reconciliation_jobs.job_id"), nullable=True)
    source = Column(String(20), nullable=False, default="synthetic")
    ai_explanation = Column(Text, nullable=True)

    # THE CRITICAL CONSTRAINT: enforces idempotency at the database level.
    # A second reconciliation run on the same data will attempt to INSERT the same
    # (transaction_id, break_type, source) tuples. These will conflict and be silently
    # skipped via ON CONFLICT DO NOTHING — no duplicates, no overwriting of manual
    # resolutions that a human may have set in between runs.
    __table_args__ = (
        UniqueConstraint("transaction_id", "break_type", "source", name="uq_break_txn_type_source"),
        Index("ix_breaks_break_type", "break_type"),
        Index("ix_breaks_resolved", "resolved"),
        Index("ix_breaks_source", "source"),
    )
