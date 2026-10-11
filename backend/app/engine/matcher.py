"""Pure reconciliation rules: duplicates, exact IDs, then greedy fallback.

Amounts must already use comparable units; no currency conversion takes place.
FX_ROUNDING is a review suggestion, not proof of the cause. Fuzzy pairs are
ranked by amount difference, UTC calendar-date difference, then external ID.
The fallback can mis-pair similar payments and has quadratic worst-case cost.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

# ─── Tolerance Constants ──────────────────────────────────────────────────────
AMOUNT_TOLERANCE = Decimal("0.50")  # ±$0.50 for fuzzy amount match
DATE_TOLERANCE_DAYS = 3  # ±3 days for fuzzy date match
FX_DELTA_THRESHOLD = Decimal("0.05")  # ≤$0.05 delta classified as FX_ROUNDING

# ─── Break Type Constants ─────────────────────────────────────────────────────
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
MISSING_INTERNAL = "MISSING_INTERNAL"
MISSING_EXTERNAL = "MISSING_EXTERNAL"
DUPLICATE = "DUPLICATE"
TIMING_LAG = "TIMING_LAG"
FX_ROUNDING = "FX_ROUNDING"
UNKNOWN = "UNKNOWN"
BREAK_TYPES = (
    AMOUNT_MISMATCH,
    MISSING_INTERNAL,
    MISSING_EXTERNAL,
    DUPLICATE,
    TIMING_LAG,
    FX_ROUNDING,
    UNKNOWN,
)


@dataclass
class InternalRow:
    transaction_id: str
    account_id: str
    amount: Decimal
    currency: str
    timestamp: datetime
    description: str
    status: str


@dataclass
class ExternalRow:
    transaction_id: str
    amount: Decimal
    timestamp: datetime
    description: str


@dataclass
class BreakRecord:
    transaction_id: str
    break_type: str
    internal_amount: Optional[Decimal] = None
    external_amount: Optional[Decimal] = None
    delta_amount: Optional[Decimal] = None
    internal_timestamp: Optional[datetime] = None
    external_timestamp: Optional[datetime] = None
    description: str = ""
    external_transaction_id: Optional[str] = None
    currency: Optional[str] = None
    evidence_side: str = "pair"
    occurrence: int = 0

    @property
    def identity(self) -> str:
        key = [self.transaction_id, self.break_type, self.evidence_side, self.occurrence]
        return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def _parse_dt(s: str) -> datetime:
    """Parse ISO timestamp to timezone-aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _date_delta_days(a: datetime, b: datetime) -> int:
    """Absolute difference in calendar days between two datetimes."""

    def utc_date(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date()

    return abs((utc_date(a) - utc_date(b)).days)


def load_internal_ledger(path: Path) -> List[InternalRow]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(
                InternalRow(
                    transaction_id=r["transaction_id"],
                    account_id=r["account_id"],
                    amount=Decimal(r["amount"]),
                    currency=r["currency"].strip().upper(),
                    timestamp=_parse_dt(r["timestamp"]),
                    description=r.get("description", ""),
                    status=r.get("status", ""),
                )
            )
    return rows


def load_external_statement(path: Path) -> List[ExternalRow]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(
                ExternalRow(
                    transaction_id=r["transaction_id"],
                    amount=Decimal(r["amount"]),
                    timestamp=_parse_dt(r["timestamp"]),
                    description=r.get("description", ""),
                )
            )
    return rows


def _classify_amount_delta(
    delta: Decimal,
    internal_currency: str,
) -> str:
    """Suggest an FX label only for a nonzero small non-USD difference."""
    abs_delta = abs(delta)
    if (
        Decimal("0") < abs_delta <= FX_DELTA_THRESHOLD
        and internal_currency.strip().upper() != "USD"
    ):
        return FX_ROUNDING
    elif abs_delta > Decimal("0"):
        return AMOUNT_MISMATCH
    return ""  # no amount issue


def run_matching(
    internal_rows: List[InternalRow],
    external_rows: List[ExternalRow],
) -> List[BreakRecord]:
    """
    Core matching function. Returns a list of BreakRecord objects.

    This function is PURE (no side effects, no DB writes). The caller is responsible
    for persisting results. This makes it independently testable.
    """
    breaks: List[BreakRecord] = []

    # ── Phase 0: Duplicate Detection ──────────────────────────────────────────
    # Find transaction_ids that appear more than once in either feed BEFORE matching.
    # The "extra" occurrences are flagged as DUPLICATE; the first occurrence participates
    # in normal matching.
    #
    # We use a seen-set approach: first occurrence is kept for matching, subsequent
    # occurrences are immediately classified as DUPLICATE.

    internal_seen: Dict[str, InternalRow] = {}
    external_seen: Dict[str, ExternalRow] = {}
    internal_duplicates: List[InternalRow] = []
    external_duplicates: List[ExternalRow] = []

    internal_deduped: List[InternalRow] = []
    for row in internal_rows:
        if row.transaction_id in internal_seen:
            internal_duplicates.append(row)
        else:
            internal_seen[row.transaction_id] = row
            internal_deduped.append(row)

    external_deduped: List[ExternalRow] = []
    for row in external_rows:
        if row.transaction_id in external_seen:
            external_duplicates.append(row)
        else:
            external_seen[row.transaction_id] = row
            external_deduped.append(row)

    # Flag duplicates
    occurrences = {}
    for row in internal_duplicates:
        occurrences[row.transaction_id] = occurrences.get(row.transaction_id, 0) + 1
        breaks.append(
            BreakRecord(
                transaction_id=row.transaction_id,
                break_type=DUPLICATE,
                internal_amount=row.amount,
                internal_timestamp=row.timestamp,
                description=f"Duplicate in internal ledger: {row.description}",
                currency=row.currency,
                evidence_side="internal",
                occurrence=occurrences[row.transaction_id],
            )
        )
    occurrences = {}
    for row in external_duplicates:
        occurrences[row.transaction_id] = occurrences.get(row.transaction_id, 0) + 1
        breaks.append(
            BreakRecord(
                transaction_id=row.transaction_id,
                break_type=DUPLICATE,
                external_amount=row.amount,
                external_timestamp=row.timestamp,
                description=f"Duplicate in external statement: {row.description}",
                external_transaction_id=row.transaction_id,
                evidence_side="external",
                occurrence=occurrences[row.transaction_id],
            )
        )

    # ── Phase 1: Exact ID Match ────────────────────────────────────────────────
    # Build lookup dict for external by transaction_id
    external_by_id: Dict[str, ExternalRow] = {r.transaction_id: r for r in external_deduped}
    internal_by_id: Dict[str, InternalRow] = {r.transaction_id: r for r in internal_deduped}

    exact_matched_internal_ids: set = set()
    exact_matched_external_ids: set = set()

    for txn_id, int_row in sorted(internal_by_id.items()):
        ext_row = external_by_id.get(txn_id)
        if ext_row is None:
            # Not matched by ID — goes to Phase 2
            continue

        exact_matched_internal_ids.add(txn_id)
        exact_matched_external_ids.add(txn_id)

        # Check amount delta
        amount_delta = int_row.amount - ext_row.amount
        break_type = _classify_amount_delta(amount_delta, int_row.currency)

        if break_type:
            breaks.append(
                BreakRecord(
                    transaction_id=txn_id,
                    break_type=break_type,
                    internal_amount=int_row.amount,
                    external_amount=ext_row.amount,
                    delta_amount=amount_delta,
                    internal_timestamp=int_row.timestamp,
                    external_timestamp=ext_row.timestamp,
                    description=f"Amount delta {amount_delta:+.4f} {int_row.currency}",
                )
            )
            # TIMING_LAG is checked independently — a transaction can have BOTH an
            # amount mismatch AND a timing lag. We classify the amount issue first and
            # note the timing separately only if amounts match.
            continue

        # Check date delta (only if amounts are clean)
        date_diff = _date_delta_days(int_row.timestamp, ext_row.timestamp)
        if 0 < date_diff <= DATE_TOLERANCE_DAYS:
            breaks.append(
                BreakRecord(
                    transaction_id=txn_id,
                    break_type=TIMING_LAG,
                    internal_amount=int_row.amount,
                    external_amount=ext_row.amount,
                    delta_amount=Decimal("0"),
                    internal_timestamp=int_row.timestamp,
                    external_timestamp=ext_row.timestamp,
                    description=f"Date differs by {date_diff} day(s) — settlement lag suspected",
                )
            )
        elif date_diff > DATE_TOLERANCE_DAYS:
            # More than DATE_TOLERANCE_DAYS apart — classify as UNKNOWN since it's outside
            # our confidence window for timing lag
            breaks.append(
                BreakRecord(
                    transaction_id=txn_id,
                    break_type=UNKNOWN,
                    internal_amount=int_row.amount,
                    external_amount=ext_row.amount,
                    delta_amount=Decimal("0"),
                    internal_timestamp=int_row.timestamp,
                    external_timestamp=ext_row.timestamp,
                    description=f"Date mismatch > {DATE_TOLERANCE_DAYS} days — not a simple timing lag",
                )
            )
        # else: date_diff == 0 → perfect match, no break

    # ── Phase 2: Fuzzy Fallback ────────────────────────────────────────────────
    # For rows not matched in Phase 1, attempt amount+date proximity matching.
    #
    # Greedy fallback scans the remaining external pool for each internal row.
    # It is quadratic in the worst case and can mis-pair similar payments.

    unmatched_internal = [
        r for r in internal_deduped if r.transaction_id not in exact_matched_internal_ids
    ]
    unmatched_external = [
        r for r in external_deduped if r.transaction_id not in exact_matched_external_ids
    ]

    fuzzy_matched_external_ids: set = set()

    for int_row in sorted(unmatched_internal, key=lambda row: row.transaction_id):
        candidates = [
            row
            for row in unmatched_external
            if row.transaction_id not in fuzzy_matched_external_ids
            and abs(int_row.amount - row.amount) <= AMOUNT_TOLERANCE
            and _date_delta_days(int_row.timestamp, row.timestamp) <= DATE_TOLERANCE_DAYS
            and int_row.amount * row.amount >= 0
        ]
        matched_ext = min(
            candidates,
            default=None,
            key=lambda row: (
                abs(int_row.amount - row.amount),
                _date_delta_days(int_row.timestamp, row.timestamp),
                row.transaction_id,
            ),
        )

        if matched_ext is not None:
            fuzzy_matched_external_ids.add(matched_ext.transaction_id)
            # Fuzzy-matched pairs — check what kind of break they represent
            amount_delta = int_row.amount - matched_ext.amount
            date_diff = _date_delta_days(int_row.timestamp, matched_ext.timestamp)
            break_type = _classify_amount_delta(amount_delta, int_row.currency)
            if not break_type and date_diff > 0:
                break_type = TIMING_LAG
            if not break_type:
                break_type = UNKNOWN

            breaks.append(
                BreakRecord(
                    transaction_id=int_row.transaction_id,
                    break_type=break_type,
                    internal_amount=int_row.amount,
                    external_amount=matched_ext.amount,
                    delta_amount=amount_delta,
                    internal_timestamp=int_row.timestamp,
                    external_timestamp=matched_ext.timestamp,
                    description=f"Suggested fuzzy pair with {matched_ext.transaction_id} (ID mismatch) — {break_type}; {len(candidates)} eligible candidate(s), review pairing",
                    external_transaction_id=matched_ext.transaction_id,
                )
            )
        else:
            # No match found in either phase → MISSING_EXTERNAL
            breaks.append(
                BreakRecord(
                    transaction_id=int_row.transaction_id,
                    break_type=MISSING_EXTERNAL,
                    internal_amount=int_row.amount,
                    internal_timestamp=int_row.timestamp,
                    description="Present in internal ledger, not found in external statement",
                    evidence_side="internal",
                )
            )

    # External rows with no internal match → MISSING_INTERNAL
    fuzzy_matched_external_ids_all = fuzzy_matched_external_ids | exact_matched_external_ids
    for ext_row in unmatched_external:
        if ext_row.transaction_id in fuzzy_matched_external_ids_all:
            continue
        breaks.append(
            BreakRecord(
                transaction_id=ext_row.transaction_id,
                break_type=MISSING_INTERNAL,
                external_amount=ext_row.amount,
                external_timestamp=ext_row.timestamp,
                description="Present in external statement, not found in internal ledger",
                evidence_side="external",
                external_transaction_id=ext_row.transaction_id,
            )
        )

    # Preserve evidence used for every exact pair and its displayed currency.
    for br in breaks:
        if br.currency is None and br.transaction_id in internal_by_id:
            br.currency = internal_by_id[br.transaction_id].currency
        if br.evidence_side == "pair" and br.external_transaction_id is None:
            if br.transaction_id in external_by_id:
                br.external_transaction_id = br.transaction_id
    return breaks
