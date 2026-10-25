"""Pure reconciliation rules: duplicates, exact IDs, optimal fallback pairs, splits.

Amounts must already use comparable units; no currency conversion takes place.
FX_ROUNDING is a review suggestion, not proof of the cause. Rows whose IDs do not
line up are paired by a minimum-cost maximum matching over amount and date
distance, so one row can no longer "steal" another's only partner. Rows still
unpaired are checked for split settlements: one line on one side that equals
the exact sum of two to four lines on the other.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# ─── Tolerance Constants ──────────────────────────────────────────────────────
AMOUNT_TOLERANCE = Decimal("0.50")  # ±$0.50 for fuzzy amount match
DATE_TOLERANCE_DAYS = 3  # ±3 days for fuzzy date match
FX_DELTA_THRESHOLD = Decimal("0.05")  # ≤$0.05 delta classified as FX_ROUNDING
SPLIT_MAX_PARTS = 4  # a split settlement groups 2–4 lines
SPLIT_CANDIDATE_LIMIT = 24  # nearest-dated lines considered per split search
SPLIT_SCAN_LIMIT = 256  # rows inspected per split search, however crowded the dates

# ─── Break Type Constants ─────────────────────────────────────────────────────
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
MISSING_INTERNAL = "MISSING_INTERNAL"
MISSING_EXTERNAL = "MISSING_EXTERNAL"
DUPLICATE = "DUPLICATE"
TIMING_LAG = "TIMING_LAG"
FX_ROUNDING = "FX_ROUNDING"
REFERENCE_MISMATCH = "REFERENCE_MISMATCH"
SPLIT_SETTLEMENT = "SPLIT_SETTLEMENT"
UNKNOWN = "UNKNOWN"
BREAK_TYPES = (
    AMOUNT_MISMATCH,
    MISSING_INTERNAL,
    MISSING_EXTERNAL,
    DUPLICATE,
    TIMING_LAG,
    FX_ROUNDING,
    REFERENCE_MISMATCH,
    SPLIT_SETTLEMENT,
    UNKNOWN,
)

# ─── Confidence ───────────────────────────────────────────────────────────────
# How strongly the evidence supports the label, so reviewers can triage. These
# are rule-based tiers, not calibrated probabilities.
HIGH, MEDIUM, LOW = "high", "medium", "low"
CONFIDENCE_LEVELS = (HIGH, MEDIUM, LOW)


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
    confidence: str = HIGH
    related_ids: Optional[List[str]] = None

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


def _utc_date(dt: datetime):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _date_delta_days(a: datetime, b: datetime) -> int:
    """Absolute difference in calendar days between two datetimes."""
    return abs((_utc_date(a) - _utc_date(b)).days)


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


# ─── Optimal pairing ──────────────────────────────────────────────────────────


def _pair_cost(internal: InternalRow, external: ExternalRow) -> int:
    """Lexicographic per-pair cost: amount distance first, then calendar days.

    Amounts have at most four decimal places, and the date window is at most
    three days, so ``units * 4 + days`` never lets dates outweigh a cent.
    """
    units = int(abs(internal.amount - external.amount).scaleb(4))
    return units * (DATE_TOLERANCE_DAYS + 1) + _date_delta_days(
        internal.timestamp, external.timestamp
    )


def min_cost_matching(left: int, right: int, edges: Sequence[tuple]) -> Dict[int, int]:
    """Maximum-cardinality matching with minimum total cost.

    ``edges`` holds ``(left_index, right_index, cost)`` with non-negative integer
    costs. Successive shortest augmenting paths (Dijkstra with Johnson
    potentials) give, after every augmentation, the cheapest matching of that
    size; running until no path remains gives the cheapest maximum matching.
    Ties resolve by index, so the result is deterministic for a given order.
    """
    source, sink = left + right, left + right + 1
    size = left + right + 2
    # graph[u] holds [to, capacity, cost, index of reverse edge in graph[to]]
    graph: List[List[list]] = [[] for _ in range(size)]

    def add(u, v, cost):
        graph[u].append([v, 1, cost, len(graph[v])])
        graph[v].append([u, 0, -cost, len(graph[u]) - 1])

    for i in range(left):
        add(source, i, 0)
    for i, j, cost in edges:
        add(i, left + j, cost)
    for j in range(right):
        add(left + j, sink, 0)

    infinity = float("inf")
    potential = [0] * size
    while True:
        dist = [infinity] * size
        previous: List[Optional[tuple]] = [None] * size
        dist[source] = 0
        heap = [(0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for index, (v, capacity, cost, _) in enumerate(graph[u]):
                if not capacity:
                    continue
                candidate = d + cost + potential[u] - potential[v]
                if candidate < dist[v]:
                    dist[v] = candidate
                    previous[v] = (u, index)
                    heapq.heappush(heap, (candidate, v))
        if dist[sink] == infinity:
            break
        # Capping at the sink distance keeps every reduced cost non-negative,
        # including for nodes this round could not reach.
        for node in range(size):
            potential[node] += min(dist[node], dist[sink])
        node = sink
        while node != source:
            u, index = previous[node]
            edge = graph[u][index]
            edge[1] -= 1
            graph[node][edge[3]][1] += 1
            node = u

    matching = {}
    for i in range(left):
        for v, capacity, _, _ in graph[i]:
            if left <= v < left + right and capacity == 0:
                matching[i] = v - left
    return matching


def _components(left: int, right: int, edges: Sequence[tuple]) -> List[tuple]:
    """Split a bipartite candidate graph into independent connected components."""
    parent = list(range(left + right))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _ in edges:
        a, b = find(i), find(left + j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups: Dict[int, tuple] = {}
    for i, j, cost in edges:
        root = find(i)
        lefts, rights, members = groups.setdefault(root, (set(), set(), []))
        lefts.add(i)
        rights.add(j)
        members.append((i, j, cost))
    return [groups[key] for key in sorted(groups)]


def _optimal_pairs(
    internal_rows: List[InternalRow], external_rows: List[ExternalRow]
) -> tuple[Dict[int, int], List[int], List[int]]:
    """Pair rows whose IDs did not match; return pairs and candidate counts."""
    order = sorted(range(len(external_rows)), key=lambda j: external_rows[j].amount)
    amounts = [external_rows[j].amount for j in order]
    edges = []
    for i, row in enumerate(internal_rows):
        low = bisect_left(amounts, row.amount - AMOUNT_TOLERANCE)
        high = bisect_right(amounts, row.amount + AMOUNT_TOLERANCE)
        for position in range(low, high):
            j = order[position]
            other = external_rows[j]
            if (
                row.amount * other.amount >= 0
                and _date_delta_days(row.timestamp, other.timestamp) <= DATE_TOLERANCE_DAYS
            ):
                edges.append((i, j, _pair_cost(row, other)))
    left_degree = [0] * len(internal_rows)
    right_degree = [0] * len(external_rows)
    for i, j, _ in edges:
        left_degree[i] += 1
        right_degree[j] += 1

    pairs: Dict[int, int] = {}
    for lefts, rights, members in _components(len(internal_rows), len(external_rows), edges):
        if len(members) == 1:
            i, j, _ = members[0]
            pairs[i] = j
            continue
        left_ids, right_ids = sorted(lefts), sorted(rights)
        left_index = {value: index for index, value in enumerate(left_ids)}
        right_index = {value: index for index, value in enumerate(right_ids)}
        local = min_cost_matching(
            len(left_ids),
            len(right_ids),
            [(left_index[i], right_index[j], cost) for i, j, cost in sorted(members)],
        )
        for i, j in local.items():
            pairs[left_ids[i]] = right_ids[j]
    return pairs, left_degree, right_degree


# ─── Split settlements ────────────────────────────────────────────────────────


def _exact_subsets(goal: Decimal, values: List[Decimal], limit: int = 2) -> List[tuple]:
    """Find up to ``limit`` index sets of 2..SPLIT_MAX_PARTS values summing to goal.

    ``values`` must be positive and sorted ascending. Fewer parts win: larger
    sets are only searched when no smaller set exists. Sorting lets the search
    stop as soon as the smallest remaining values would overshoot, or skip a
    branch whose largest values cannot reach the goal.
    """
    found: List[tuple] = []
    count = len(values)
    prefix = [Decimal("0")]
    for value in values:
        prefix.append(prefix[-1] + value)

    def search(start, parts, remaining, chosen):
        if len(found) >= limit or count - start < parts:
            return
        if prefix[count] - prefix[count - parts] < remaining:
            return
        if parts == 1:
            position = bisect_left(values, remaining, lo=start)
            while position < len(values) and values[position] == remaining:
                found.append(chosen + (position,))
                if len(found) >= limit:
                    return
                position += 1
            return
        for index in range(start, len(values)):
            if values[index] * parts > remaining:
                break
            search(index + 1, parts - 1, remaining - values[index], chosen + (index,))
            if len(found) >= limit:
                return

    for parts in range(2, SPLIT_MAX_PARTS + 1):
        search(0, parts, goal, ())
        if found:
            break
    return found


class _DatePool:
    """Rows sorted by UTC calendar day, so a date window is two binary searches."""

    def __init__(self, rows):
        self.rows = sorted(
            rows, key=lambda row: (_utc_date(row.timestamp).toordinal(), row.transaction_id)
        )
        self.days = [_utc_date(row.timestamp).toordinal() for row in self.rows]

    def nearest(self, timestamp, accept, limit):
        """Up to ``limit`` accepted rows inside the date window, nearest day first.

        At most SPLIT_SCAN_LIMIT rows are inspected, which bounds the cost of a
        search when thousands of rows share a date.
        """
        day = _utc_date(timestamp).toordinal()
        low = bisect_left(self.days, day - DATE_TOLERANCE_DAYS)
        high = bisect_right(self.days, day + DATE_TOLERANCE_DAYS)
        right = bisect_left(self.days, day, low, high)
        left = right - 1
        found, inspected = [], 0
        while (left >= low or right < high) and len(found) < limit:
            if inspected >= SPLIT_SCAN_LIMIT:
                break
            take_right = left < low or (
                right < high and self.days[right] - day <= day - self.days[left]
            )
            if take_right:
                row, right = self.rows[right], right + 1
            else:
                row, left = self.rows[left], left - 1
            inspected += 1
            if accept(row):
                found.append(row)
        return found


def _find_split(target, pool: _DatePool, eligible) -> tuple[Optional[list], bool]:
    """Return the rows in ``pool`` that settle ``target`` exactly, and ambiguity."""

    def accept(row):
        return (
            eligible(row)
            and row.amount * target.amount > 0
            and abs(row.amount) < abs(target.amount)
        )

    candidates = pool.nearest(target.timestamp, accept, SPLIT_CANDIDATE_LIMIT)
    if len(candidates) < 2:
        return None, False
    candidates.sort(key=lambda row: (abs(row.amount), row.transaction_id))
    solutions = _exact_subsets(abs(target.amount), [abs(row.amount) for row in candidates])
    if not solutions:
        return None, False
    return [candidates[index] for index in solutions[0]], len(solutions) > 1


def _ids(rows) -> str:
    return ", ".join(row.transaction_id for row in rows)


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
    # The first occurrence of each transaction ID takes part in matching; every
    # later occurrence on the same side is reported as a DUPLICATE.

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

    # An extra copy with the same amount is almost certainly a reprocessed row;
    # a different amount under a reused ID needs a closer look.
    occurrences = {}
    for row in internal_duplicates:
        occurrences[row.transaction_id] = occurrences.get(row.transaction_id, 0) + 1
        same = row.amount == internal_seen[row.transaction_id].amount
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
                confidence=HIGH if same else MEDIUM,
            )
        )
    occurrences = {}
    for row in external_duplicates:
        occurrences[row.transaction_id] = occurrences.get(row.transaction_id, 0) + 1
        same = row.amount == external_seen[row.transaction_id].amount
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
                confidence=HIGH if same else MEDIUM,
            )
        )

    # ── Phase 1: Exact ID Match ────────────────────────────────────────────────
    external_by_id: Dict[str, ExternalRow] = {r.transaction_id: r for r in external_deduped}
    internal_by_id: Dict[str, InternalRow] = {r.transaction_id: r for r in internal_deduped}

    exact_matched_ids: set = set()

    for txn_id, int_row in sorted(internal_by_id.items()):
        ext_row = external_by_id.get(txn_id)
        if ext_row is None:
            # Not matched by ID — goes to Phase 2
            continue

        exact_matched_ids.add(txn_id)

        # Amount differences are classified first; a timing difference is only
        # reported on its own when the amounts agree.
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
                    confidence=MEDIUM if break_type == FX_ROUNDING else HIGH,
                )
            )
            continue

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
            # Too far apart to call a settlement lag with any confidence.
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
                    confidence=LOW,
                )
            )
        # else: date_diff == 0 → perfect match, no break

    # ── Phase 2: Optimal fallback pairing ─────────────────────────────────────
    # Banks rarely echo the ledger's own reference, so rows without an ID match
    # are paired on amount (±AMOUNT_TOLERANCE) and date (±DATE_TOLERANCE_DAYS).
    # A greedy pass lets an early row take a later row's only partner; instead
    # the candidate graph is split into connected components and each one is
    # solved as a minimum-cost maximum matching. Every pair is a suggestion.

    unmatched_internal = sorted(
        (r for r in internal_deduped if r.transaction_id not in exact_matched_ids),
        key=lambda row: row.transaction_id,
    )
    unmatched_external = sorted(
        (r for r in external_deduped if r.transaction_id not in exact_matched_ids),
        key=lambda row: row.transaction_id,
    )
    pairs, internal_degree, external_degree = _optimal_pairs(unmatched_internal, unmatched_external)

    for i, j in sorted(pairs.items()):
        int_row, matched_ext = unmatched_internal[i], unmatched_external[j]
        amount_delta = int_row.amount - matched_ext.amount
        date_diff = _date_delta_days(int_row.timestamp, matched_ext.timestamp)
        break_type = _classify_amount_delta(amount_delta, int_row.currency)
        if not break_type and date_diff > 0:
            break_type = TIMING_LAG
        if not break_type:
            break_type = REFERENCE_MISMATCH
        unique = internal_degree[i] == 1 and external_degree[j] == 1
        if unique and break_type == REFERENCE_MISMATCH:
            confidence = HIGH
        elif unique and break_type != FX_ROUNDING:
            confidence = MEDIUM
        else:
            confidence = LOW
        candidates = internal_degree[i]
        breaks.append(
            BreakRecord(
                transaction_id=int_row.transaction_id,
                break_type=break_type,
                internal_amount=int_row.amount,
                external_amount=matched_ext.amount,
                delta_amount=amount_delta,
                internal_timestamp=int_row.timestamp,
                external_timestamp=matched_ext.timestamp,
                description=(
                    f"Paired with bank reference {matched_ext.transaction_id} on amount and date "
                    f"(IDs differ) — {break_type}; {candidates} eligible candidate(s), "
                    "review pairing"
                ),
                external_transaction_id=matched_ext.transaction_id,
                confidence=confidence,
            )
        )

    # ── Phase 3: Split settlements ────────────────────────────────────────────
    # A bank often settles several ledger entries in one deposit, and a single
    # invoice can be paid in instalments. Remaining lines that sum exactly to a
    # line on the other side, within the date window, are grouped.

    left_internal = [row for i, row in enumerate(unmatched_internal) if i not in pairs]
    paired_external = set(pairs.values())
    left_external = [row for j, row in enumerate(unmatched_external) if j not in paired_external]
    used_internal: set = set()
    used_external: set = set()

    internal_pools = {}
    for row in left_internal:
        internal_pools.setdefault(row.currency, []).append(row)
    internal_pools = {currency: _DatePool(rows) for currency, rows in internal_pools.items()}
    external_pool = _DatePool(left_external)

    for target in left_external:
        best, ambiguous = None, False
        for currency in sorted(internal_pools):
            members, unclear = _find_split(
                target,
                internal_pools[currency],
                lambda row: row.transaction_id not in used_internal,
            )
            if members and (best is None or len(members) < len(best)):
                best, ambiguous = members, unclear
        if not best:
            continue
        used_external.add(target.transaction_id)
        used_internal.update(row.transaction_id for row in best)
        total = sum((row.amount for row in best), Decimal("0"))
        breaks.append(
            BreakRecord(
                transaction_id=target.transaction_id,
                break_type=SPLIT_SETTLEMENT,
                internal_amount=total,
                external_amount=target.amount,
                delta_amount=Decimal("0"),
                internal_timestamp=max(row.timestamp for row in best),
                external_timestamp=target.timestamp,
                description=(
                    f"One bank line settles {len(best)} ledger entries ({_ids(best)}) "
                    "whose amounts sum exactly to it"
                    + (
                        "; another combination also fits, check the remittance advice"
                        if ambiguous
                        else ""
                    )
                ),
                external_transaction_id=target.transaction_id,
                currency=best[0].currency,
                evidence_side="many_internal",
                confidence=LOW if ambiguous else MEDIUM,
                related_ids=sorted(row.transaction_id for row in best),
            )
        )

    for target in left_internal:
        if target.transaction_id in used_internal:
            continue
        members, ambiguous = _find_split(
            target,
            external_pool,
            lambda row: row.transaction_id not in used_external,
        )
        if not members:
            continue
        used_internal.add(target.transaction_id)
        used_external.update(row.transaction_id for row in members)
        total = sum((row.amount for row in members), Decimal("0"))
        breaks.append(
            BreakRecord(
                transaction_id=target.transaction_id,
                break_type=SPLIT_SETTLEMENT,
                internal_amount=target.amount,
                external_amount=total,
                delta_amount=Decimal("0"),
                internal_timestamp=target.timestamp,
                external_timestamp=max(row.timestamp for row in members),
                description=(
                    f"One ledger entry is settled by {len(members)} bank lines ({_ids(members)}) "
                    "whose amounts sum exactly to it"
                    + (
                        "; another combination also fits, check the remittance advice"
                        if ambiguous
                        else ""
                    )
                ),
                currency=target.currency,
                evidence_side="many_external",
                confidence=LOW if ambiguous else MEDIUM,
                related_ids=sorted(row.transaction_id for row in members),
            )
        )

    # ── Phase 4: Leftovers ────────────────────────────────────────────────────
    # A row that had a nearby candidate which was paired elsewhere is less
    # certainly missing than one with nothing close at all.
    for i, row in enumerate(unmatched_internal):
        if i in pairs or row.transaction_id in used_internal:
            continue
        breaks.append(
            BreakRecord(
                transaction_id=row.transaction_id,
                break_type=MISSING_EXTERNAL,
                internal_amount=row.amount,
                internal_timestamp=row.timestamp,
                description="Present in internal ledger, not found in external statement",
                evidence_side="internal",
                confidence=MEDIUM if internal_degree[i] else HIGH,
            )
        )
    for j, row in enumerate(unmatched_external):
        if j in paired_external or row.transaction_id in used_external:
            continue
        breaks.append(
            BreakRecord(
                transaction_id=row.transaction_id,
                break_type=MISSING_INTERNAL,
                external_amount=row.amount,
                external_timestamp=row.timestamp,
                description="Present in external statement, not found in internal ledger",
                evidence_side="external",
                external_transaction_id=row.transaction_id,
                confidence=MEDIUM if external_degree[j] else HIGH,
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
