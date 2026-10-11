"""Portable UUIDs and exact four-decimal amounts."""

import uuid
from datetime import timezone
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, DateTime, Numeric, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

QUANTUM = Decimal("0.0001")
MAX_AMOUNT = Decimal("99999999999999.9999")


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(
            PG_UUID(as_uuid=True) if dialect.name == "postgresql" else CHAR(36)
        )

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return uuid.UUID(str(value)) if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        return uuid.UUID(str(value)) if value is not None else None


class Money(TypeDecorator):
    """SQLite stores scaled integers; PostgreSQL uses NUMERIC(18,4).

    SQLite NUMERIC affinity otherwise converts decimals to binary floating point.
    All application queries must go through typed SQLAlchemy columns.
    """

    impl = Numeric(18, 4)
    cache_ok = True

    def __init__(self, *, delta=False):
        super().__init__()
        self.delta = delta

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(
            BigInteger() if dialect.name == "sqlite" else Numeric(19 if self.delta else 18, 4)
        )

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        amount = Decimal(str(value))
        if (
            not amount.is_finite()
            or abs(amount) > MAX_AMOUNT * (2 if self.delta else 1)
            or amount != amount.quantize(QUANTUM)
        ):
            raise ValueError(
                "Amount must be finite, within 14 integer digits and at most 4 decimal places"
            )
        return int(amount * 10000) if dialect.name == "sqlite" else amount

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value).scaleb(-4) if dialect.name == "sqlite" else Decimal(value)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(
            timezone.utc
        )
