# Frozen schema for revision 0001_reconciliation. Do not edit when changing app.models.
"""Persistence schema. Dataset locks serialize replacement and job admission."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base

from app.dbtypes import GUID, Money, UTCDateTime

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class DatasetState(Base):
    __tablename__ = "dataset_state"
    source = Column(String(20), primary_key=True)
    ledger_hash = Column(String(64), nullable=True)
    statement_hash = Column(String(64), nullable=True)
    ledger_rows = Column(Integer, nullable=False, default=0)
    statement_rows = Column(Integer, nullable=False, default=0)


class LedgerTransaction(Base):
    # Retained for upgrades of the original schema. Synthetic runs read the CSVs.
    __tablename__ = "ledger"
    transaction_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False)
    amount = Column(Money(), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    timestamp = Column(UTCDateTime(), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default="settled")


class UploadedLedgerTransaction(Base):
    __tablename__ = "uploaded_ledger"
    row_id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=False)
    amount = Column(Money(), nullable=False)
    currency = Column(String(3), nullable=False)
    timestamp = Column(UTCDateTime(), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default="settled")


class UploadedStatementTransaction(Base):
    __tablename__ = "uploaded_statement"
    row_id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, nullable=False, index=True)
    amount = Column(Money(), nullable=False)
    timestamp = Column(UTCDateTime(), nullable=False)
    description = Column(Text)


class ReconciliationJob(Base):
    __tablename__ = "reconciliation_jobs"
    job_id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    status = Column(String(20), nullable=False, default="pending")
    source = Column(String(20), nullable=False, default="synthetic")
    started_at = Column(UTCDateTime())
    finished_at = Column(UTCDateTime())
    error_message = Column(Text)
    transactions_processed = Column(Integer)
    breaks_detected = Column(Integer)
    breaks_inserted = Column(Integer)
    __table_args__ = (
        Index(
            "uq_active_job_source",
            "source",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )


class ReconciliationBreak(Base):
    __tablename__ = "reconciliation_breaks"
    break_id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    break_key = Column(String(64), nullable=False)
    transaction_id = Column(String, nullable=False)
    external_transaction_id = Column(String)
    break_type = Column(String(30), nullable=False)
    currency = Column(String(3))
    evidence_side = Column(String(20), nullable=False, default="pair")
    occurrence = Column(Integer, nullable=False, default=0)
    internal_amount = Column(Money())
    external_amount = Column(Money())
    delta_amount = Column(Money(delta=True))
    internal_timestamp = Column(UTCDateTime())
    external_timestamp = Column(UTCDateTime())
    description = Column(Text)
    detected_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(UTCDateTime())
    job_id = Column(GUID(), ForeignKey("reconciliation_jobs.job_id"))
    source = Column(String(20), nullable=False, default="synthetic")
    ai_explanation = Column(Text)
    __table_args__ = (
        UniqueConstraint("source", "break_key", name="uq_break_source_key"),
        Index("ix_breaks_source_resolved_type", "source", "resolved", "break_type"),
    )
