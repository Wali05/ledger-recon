"""
Ledger Reconciliation Matching Engine.

MATCHING STRATEGY:
  Phase 1 — Exact ID match:
    Join internal ledger and external bank statement on transaction_id.
    For each matched pair:
      - Check amount delta → AMOUNT_MISMATCH or FX_ROUNDING
      - Check date delta   → TIMING_LAG
    Rows that appear more than once in either feed → DUPLICATE

  Phase 2 — Fuzzy fallback:
    For rows that had no exact ID match, attempt to pair on:
      amount within ±$0.50 AND date within ±3 days.
    This handles cases where IDs were mangled or omitted by the bank's system.
    Still-unmatched internal rows → MISSING_EXTERNAL
    Still-unmatched external rows → MISSING_INTERNAL

TOLERANCE VALUES (documented explicitly per spec requirement):
  AMOUNT_TOLERANCE   = $0.50  — chosen to capture bank fee deductions without
                                false-positiving on genuinely different transactions
  DATE_TOLERANCE     = 3 days — covers standard T+2 settlement lag plus one day buffer
  FX_DELTA_THRESHOLD = $0.05  — FX rounding errors are typically sub-cent; $0.05
                                is deliberately conservative to minimise false positives

LIMITATIONS (documented per spec):
  - Fuzzy matching is greedy (first match wins), not optimal. True optimal matching
    would use the Hungarian algorithm, which is O(n³) and inappropriate for large feeds.
  - FX_ROUNDING detection requires the internal ledger row to have a non-USD currency.
    If the internal system normalised the currency to USD at booking time, FX rounding
    breaks will be misclassified as AMOUNT_MISMATCH.
  - TIMING_LAG detection requires the amounts to match exactly. If a transaction has
    BOTH a timing lag AND a small amount difference, it will be classified as
    AMOUNT_MISMATCH (first classification wins).
  - The $0.50 fuzzy amount tolerance means two genuinely different small transactions
    with similar amounts and dates could be incorrectly matched in Phase 2.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Tolerance Constants ──────────────────────────────────────────────────────
AMOUNT_TOLERANCE = Decimal("0.50")       # ±$0.50 for fuzzy amount match
DATE_TOLERANCE_DAYS = 3                  # ±3 days for fuzzy date match
FX_DELTA_THRESHOLD = Decimal("0.05")    # ≤$0.05 delta classified as FX_ROUNDING

# ─── Break Type Constants ─────────────────────────────────────────────────────
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
MISSING_INTERNAL = "MISSING_INTERNAL"
MISSING_EXTERNAL = "MISSING_EXTERNAL"
DUPLICATE = "DUPLICATE"
TIMING_LAG = "TIMING_LAG"
FX_ROUNDING = "FX_ROUNDING"
UNKNOWN = "UNKNOWN"


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


def _parse_dt(s: str) -> datetime:
    """Parse ISO timestamp to timezone-aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _date_delta_days(a: datetime, b: datetime) -> int:
    """Absolute difference in calendar days between two datetimes."""
    return abs((a.date() - b.date()).days)


def load_internal_ledger(path: Path) -> List[InternalRow]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(InternalRow(
                transaction_id=r["transaction_id"],
                account_id=r["account_id"],
                amount=Decimal(r["amount"]),
                currency=r["currency"],
                timestamp=_parse_dt(r["timestamp"]),
                description=r.get("description", ""),
                status=r.get("status", ""),
            ))
    return rows


def load_external_statement(path: Path) -> List[ExternalRow]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(ExternalRow(
                transaction_id=r["transaction_id"],
                amount=Decimal(r["amount"]),
                timestamp=_parse_dt(r["timestamp"]),
                description=r.get("description", ""),
            ))
    return rows


def _classify_amount_delta(
    delta: Decimal,
    internal_currency: str,
) -> str:
    """
    Classify an amount delta between a matched internal/external pair.

    FX_ROUNDING: delta ≤ FX_DELTA_THRESHOLD AND internal currency is non-USD.
      Rationale: small deltas on non-USD transactions are almost always FX conversion
      artefacts. The $0.05 ceiling is deliberately conservative.

    AMOUNT_MISMATCH: delta > FX_DELTA_THRESHOLD, or delta is small but currency IS USD
      (in which case there's no FX explanation).

    LIMITATION: if the internal system stores everything in USD (normalised at booking),
    FX rounding will fall through to AMOUNT_MISMATCH because the currency flag is lost.
    """
    abs_delta = abs(delta)
    if abs_delta <= FX_DELTA_THRESHOLD and internal_currency != "USD":
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
    for row in internal_duplicates:
        breaks.append(BreakRecord(
            transaction_id=row.transaction_id,
            break_type=DUPLICATE,
            internal_amount=row.amount,
            internal_timestamp=row.timestamp,
            description=f"Duplicate in internal ledger: {row.description}",
        ))
    for row in external_duplicates:
        breaks.append(BreakRecord(
            transaction_id=row.transaction_id,
            break_type=DUPLICATE,
            external_amount=row.amount,
            external_timestamp=row.timestamp,
            description=f"Duplicate in external statement: {row.description}",
        ))

    # ── Phase 1: Exact ID Match ────────────────────────────────────────────────
    # Build lookup dict for external by transaction_id
    external_by_id: Dict[str, ExternalRow] = {r.transaction_id: r for r in external_deduped}
    internal_by_id: Dict[str, InternalRow] = {r.transaction_id: r for r in internal_deduped}

    exact_matched_internal_ids: set = set()
    exact_matched_external_ids: set = set()

    for txn_id, int_row in internal_by_id.items():
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
            breaks.append(BreakRecord(
                transaction_id=txn_id,
                break_type=break_type,
                internal_amount=int_row.amount,
                external_amount=ext_row.amount,
                delta_amount=amount_delta,
                internal_timestamp=int_row.timestamp,
                external_timestamp=ext_row.timestamp,
                description=f"Amount delta {amount_delta:+.4f} {int_row.currency}",
            ))
            # TIMING_LAG is checked independently — a transaction can have BOTH an
            # amount mismatch AND a timing lag. We classify the amount issue first and
            # note the timing separately only if amounts match.
            continue

        # Check date delta (only if amounts are clean)
        date_diff = _date_delta_days(int_row.timestamp, ext_row.timestamp)
        if 0 < date_diff <= DATE_TOLERANCE_DAYS:
            breaks.append(BreakRecord(
                transaction_id=txn_id,
                break_type=TIMING_LAG,
                internal_amount=int_row.amount,
                external_amount=ext_row.amount,
                delta_amount=Decimal("0"),
                internal_timestamp=int_row.timestamp,
                external_timestamp=ext_row.timestamp,
                description=f"Date differs by {date_diff} day(s) — settlement lag suspected",
            ))
        elif date_diff > DATE_TOLERANCE_DAYS:
            # More than DATE_TOLERANCE_DAYS apart — classify as UNKNOWN since it's outside
            # our confidence window for timing lag
            breaks.append(BreakRecord(
                transaction_id=txn_id,
                break_type=UNKNOWN,
                internal_amount=int_row.amount,
                external_amount=ext_row.amount,
                delta_amount=Decimal("0"),
                internal_timestamp=int_row.timestamp,
                external_timestamp=ext_row.timestamp,
                description=f"Date mismatch > {DATE_TOLERANCE_DAYS} days — not a simple timing lag",
            ))
        # else: date_diff == 0 → perfect match, no break

    # ── Phase 2: Fuzzy Fallback ────────────────────────────────────────────────
    # For rows not matched in Phase 1, attempt amount+date proximity matching.
    #
    # This is a GREEDY matching algorithm (O(n²) in the worst case):
    # for each unmatched internal row, we scan all unmatched external rows and
    # take the first one within tolerance. This is NOT optimal — optimal would be
    # the Hungarian algorithm (O(n³)), which is too expensive for large feeds.
    #
    # Documented limitation: greedy fuzzy matching can produce incorrect pairings
    # when many unmatched rows have similar amounts and dates.

    unmatched_internal = [
        r for r in internal_deduped if r.transaction_id not in exact_matched_internal_ids
    ]
    unmatched_external = [
        r for r in external_deduped if r.transaction_id not in exact_matched_external_ids
    ]

    fuzzy_matched_external_ids: set = set()

    for int_row in unmatched_internal:
        matched_ext: Optional[ExternalRow] = None
        for ext_row in unmatched_external:
            if ext_row.transaction_id in fuzzy_matched_external_ids:
                continue
            amount_diff = abs(int_row.amount - ext_row.amount)
            date_diff = _date_delta_days(int_row.timestamp, ext_row.timestamp)
            if amount_diff <= AMOUNT_TOLERANCE and date_diff <= DATE_TOLERANCE_DAYS:
                matched_ext = ext_row
                break  # greedy: take first match

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

            breaks.append(BreakRecord(
                transaction_id=int_row.transaction_id,
                break_type=break_type,
                internal_amount=int_row.amount,
                external_amount=matched_ext.amount,
                delta_amount=amount_delta,
                internal_timestamp=int_row.timestamp,
                external_timestamp=matched_ext.timestamp,
                description=f"Fuzzy match (ID mismatch) — {break_type}",
            ))
        else:
            # No match found in either phase → MISSING_EXTERNAL
            breaks.append(BreakRecord(
                transaction_id=int_row.transaction_id,
                break_type=MISSING_EXTERNAL,
                internal_amount=int_row.amount,
                internal_timestamp=int_row.timestamp,
                description="Present in internal ledger, not found in external statement",
            ))

    # External rows with no internal match → MISSING_INTERNAL
    fuzzy_matched_external_ids_all = fuzzy_matched_external_ids | exact_matched_external_ids
    for ext_row in unmatched_external:
        if ext_row.transaction_id in fuzzy_matched_external_ids_all:
            continue
        breaks.append(BreakRecord(
            transaction_id=ext_row.transaction_id,
            break_type=MISSING_INTERNAL,
            external_amount=ext_row.amount,
            external_timestamp=ext_row.timestamp,
            description="Present in external statement, not found in internal ledger",
        ))

    return breaks
