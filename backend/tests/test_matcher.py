"""
Unit tests for the matching engine.

These test run_matching() directly. That is possible because the engine is a
PURE function — it takes two lists of rows and returns a list of BreakRecords
with no database, no network, and no global state. Every test below constructs
a tiny two-row scenario, runs the real engine, and asserts on the break type.

Run with:  pytest backend/tests -v
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.engine.matcher import (
    AMOUNT_MISMATCH,
    CONFIDENCE_LEVELS,
    DUPLICATE,
    FX_ROUNDING,
    HIGH,
    LOW,
    MEDIUM,
    MISSING_EXTERNAL,
    MISSING_INTERNAL,
    REFERENCE_MISMATCH,
    SPLIT_SETTLEMENT,
    TIMING_LAG,
    UNKNOWN,
    ExternalRow,
    InternalRow,
    run_matching,
)

BASE = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def internal(txn_id, amount, currency="USD", ts=None):
    return InternalRow(
        transaction_id=txn_id,
        account_id="ACC0001",
        amount=Decimal(str(amount)),
        currency=currency,
        timestamp=ts or BASE,
        description="test row",
        status="settled",
    )


def external(txn_id, amount, ts=None):
    return ExternalRow(
        transaction_id=txn_id,
        amount=Decimal(str(amount)),
        timestamp=ts or BASE,
        description="test row",
    )


def types_of(breaks):
    return [b.break_type for b in breaks]


# ── The happy path ───────────────────────────────────────────────────────────


def test_identical_rows_produce_no_breaks():
    breaks = run_matching([internal("T1", "100.00")], [external("T1", "100.00")])
    assert breaks == []


@pytest.mark.parametrize("currency", ["EUR", "GBP", "JPY", "usd", " eur "])
def test_zero_delta_is_never_fx_rounding(currency):
    assert run_matching([internal("T1", "100", currency=currency)], [external("T1", "100")]) == []


def test_same_instant_in_different_offsets_has_no_timing_break():
    a = datetime.fromisoformat("2024-06-01T23:30:00-02:00")
    b = datetime.fromisoformat("2024-06-02T01:30:00+00:00")
    assert run_matching([internal("T1", "1", ts=a)], [external("T1", "1", ts=b)]) == []


def test_duplicate_occurrences_on_both_sides_have_distinct_stable_identities():
    rows = run_matching([internal("T1", "1")] * 3, [external("T1", "1")] * 3)
    assert len(rows) == len({row.identity for row in rows}) == 4


def test_fuzzy_pairing_is_independent_of_external_order_and_retains_partner_id():
    a, b = external("A", "10.40"), external("B", "10.10")
    for candidates in ([a, b], [b, a]):
        result = run_matching([internal("T1", "10.00")], candidates)
        pair = next(row for row in result if row.transaction_id == "T1")
        assert pair.external_transaction_id == "B"


def test_fuzzy_matching_does_not_pair_opposite_signed_payments():
    result = run_matching([internal("T1", "0.10")], [external("T2", "-0.10")])
    assert set(types_of(result)) == {MISSING_INTERNAL, MISSING_EXTERNAL}


# ── One test per break type ──────────────────────────────────────────────────


def test_amount_difference_is_amount_mismatch():
    breaks = run_matching([internal("T1", "100.00")], [external("T1", "98.00")])
    assert types_of(breaks) == [AMOUNT_MISMATCH]
    assert breaks[0].delta_amount == Decimal("2.00")


def test_small_delta_on_non_usd_is_fx_rounding():
    breaks = run_matching(
        [internal("T1", "100.00", currency="EUR")],
        [external("T1", "100.03")],
    )
    assert types_of(breaks) == [FX_ROUNDING]


def test_small_delta_on_usd_is_amount_mismatch_not_fx():
    """The FX rule requires a foreign currency. A 3-cent gap on a USD
    transaction has no FX explanation, so it must stay an amount mismatch."""
    breaks = run_matching([internal("T1", "100.00")], [external("T1", "100.03")])
    assert types_of(breaks) == [AMOUNT_MISMATCH]


def test_large_delta_on_non_usd_is_amount_mismatch():
    """Above the $0.05 ceiling the FX explanation no longer applies, even for a
    foreign currency. This is a documented recall limitation, asserted here so a
    future change to the threshold cannot silently alter behaviour."""
    breaks = run_matching(
        [internal("T1", "100.00", currency="GBP")],
        [external("T1", "100.40")],
    )
    assert types_of(breaks) == [AMOUNT_MISMATCH]


def test_date_gap_within_window_is_timing_lag():
    breaks = run_matching(
        [internal("T1", "100.00")],
        [external("T1", "100.00", ts=BASE + timedelta(days=2))],
    )
    assert types_of(breaks) == [TIMING_LAG]


def test_date_gap_beyond_window_is_unknown():
    breaks = run_matching(
        [internal("T1", "100.00")],
        [external("T1", "100.00", ts=BASE + timedelta(days=10))],
    )
    assert types_of(breaks) == [UNKNOWN]


def test_row_only_in_ledger_is_missing_external():
    breaks = run_matching([internal("T1", "100.00")], [])
    assert types_of(breaks) == [MISSING_EXTERNAL]


def test_row_only_in_bank_is_missing_internal():
    breaks = run_matching([], [external("T1", "100.00")])
    assert types_of(breaks) == [MISSING_INTERNAL]


def test_repeated_id_in_bank_feed_flags_extra_copies_only():
    """Three copies of one ID means the first is kept for matching and the two
    extras are flagged — two DUPLICATE breaks, not three."""
    breaks = run_matching(
        [internal("T1", "100.00")],
        [external("T1", "100.00"), external("T1", "100.00"), external("T1", "100.00")],
    )
    assert types_of(breaks).count(DUPLICATE) == 2


# ── Phase 2: fuzzy fallback ──────────────────────────────────────────────────


def test_mangled_id_is_recovered_by_fuzzy_match():
    """IDs don't line up, but the amount and date are close enough that Phase 2
    pairs them rather than reporting two separate 'missing' breaks."""
    breaks = run_matching(
        [internal("LEDGER-1", "500.00")],
        [external("BANK-XYZ", "500.20", ts=BASE + timedelta(days=1))],
    )
    assert types_of(breaks) == [AMOUNT_MISMATCH]
    assert MISSING_EXTERNAL not in types_of(breaks)
    assert MISSING_INTERNAL not in types_of(breaks)


def test_fuzzy_match_respects_amount_tolerance():
    """$5.00 apart is outside the $0.50 window, so these must NOT be paired —
    they are two unrelated transactions, reported as missing on both sides."""
    breaks = run_matching(
        [internal("LEDGER-1", "500.00")],
        [external("BANK-XYZ", "505.00")],
    )
    assert sorted(types_of(breaks)) == sorted([MISSING_EXTERNAL, MISSING_INTERNAL])


def test_fuzzy_match_respects_date_tolerance():
    """Same amount but 30 days apart — outside the 3-day window, so no pairing."""
    breaks = run_matching(
        [internal("LEDGER-1", "500.00")],
        [external("BANK-XYZ", "500.00", ts=BASE + timedelta(days=30))],
    )
    assert sorted(types_of(breaks)) == sorted([MISSING_EXTERNAL, MISSING_INTERNAL])


# ── Determinism ──────────────────────────────────────────────────────────────


def test_engine_is_deterministic():
    """Same input, same output. This is what makes the idempotent DB insert
    meaningful: a re-run produces an identical set of natural keys."""
    ledger = [internal("T1", "100.00"), internal("T2", "50.00")]
    bank = [external("T1", "98.00")]
    first = run_matching(ledger, bank)
    second = run_matching(ledger, bank)

    def key(bs):
        return sorted((b.transaction_id, b.break_type) for b in bs)

    assert key(first) == key(second)


@pytest.mark.parametrize("currency", ["EUR", "GBP", "JPY", "CAD"])
def test_fx_rule_applies_to_any_non_usd_currency(currency):
    breaks = run_matching(
        [internal("T1", "200.00", currency=currency)],
        [external("T1", "200.02")],
    )
    assert types_of(breaks) == [FX_ROUNDING]


def _greedy_fuzzy_pairs(internal_rows, external_rows):
    """The previous fallback: each ledger row, in ID order, takes its closest row."""
    from app.engine.matcher import AMOUNT_TOLERANCE, DATE_TOLERANCE_DAYS, _date_delta_days

    used, pairs = set(), {}
    for int_row in sorted(internal_rows, key=lambda row: row.transaction_id):
        candidates = [
            row
            for row in external_rows
            if row.transaction_id not in used
            and abs(int_row.amount - row.amount) <= AMOUNT_TOLERANCE
            and _date_delta_days(int_row.timestamp, row.timestamp) <= DATE_TOLERANCE_DAYS
            and int_row.amount * row.amount >= 0
        ]
        if candidates:
            best = min(
                candidates,
                key=lambda row: (
                    abs(int_row.amount - row.amount),
                    _date_delta_days(int_row.timestamp, row.timestamp),
                    row.transaction_id,
                ),
            )
            used.add(best.transaction_id)
            pairs[int_row.transaction_id] = best.transaction_id
    return pairs


def _fuzzy_pairs(records):
    return {
        record.transaction_id: record.external_transaction_id
        for record in records
        if record.external_transaction_id
        and record.evidence_side == "pair"
        and record.external_transaction_id != record.transaction_id
    }


def _random_rows(rng, count, prefix, factory):
    return [
        factory(
            f"{prefix}{i:04d}",
            Decimal(rng.randint(-3000, 3000)) / 100,
            ts=BASE + timedelta(days=rng.randint(0, 8)),
        )
        for i in range(count)
    ]


def test_optimal_pairing_does_not_let_one_row_steal_anothers_only_partner():
    """Greedy pairs A with its closest row X, leaving B with nothing in range.
    The optimal matching pairs both: A with Y and B with X."""
    ledger = [internal("A", "100.20"), internal("B", "100.00")]
    bank = [external("X", "100.10"), external("Y", "100.60")]
    assert _greedy_fuzzy_pairs(ledger, bank) == {"A": "X"}
    breaks = run_matching(ledger, bank)
    assert _fuzzy_pairs(breaks) == {"A": "Y", "B": "X"}
    assert MISSING_EXTERNAL not in types_of(breaks)
    assert MISSING_INTERNAL not in types_of(breaks)


@pytest.mark.parametrize("seed", range(40))
def test_fallback_finds_the_cheapest_maximum_matching(seed):
    """Brute force every assignment on small dense instances."""
    import itertools
    import random

    from app.engine.matcher import _pair_cost

    rng = random.Random(seed)
    ledger = _random_rows(rng, rng.randint(1, 6), "I", internal)
    bank = _random_rows(rng, rng.randint(1, 6), "E", external)
    for row in ledger + bank:
        row.amount = Decimal(rng.randint(0, 120)) / 100  # crowd the ±0.50 window
    edge = {}
    for a in ledger:
        for b in bank:
            if run_matching([a], [b]) and not {
                MISSING_EXTERNAL,
                MISSING_INTERNAL,
            } & set(types_of(run_matching([a], [b]))):
                edge[a.transaction_id, b.transaction_id] = _pair_cost(a, b)
    best = (0, 0)
    for size in range(1, min(len(ledger), len(bank)) + 1):
        for chosen in itertools.combinations(ledger, size):
            for partners in itertools.permutations(bank, size):
                keys = [(a.transaction_id, b.transaction_id) for a, b in zip(chosen, partners)]
                if all(key in edge for key in keys):
                    best = max(best, (size, -sum(edge[key] for key in keys)))
    actual = _fuzzy_pairs(run_matching(ledger, bank))
    cost = sum(edge[pair] for pair in actual.items())
    assert (len(actual), -cost) == best


@pytest.mark.parametrize("seed", range(3))
def test_optimal_fallback_pairs_at_least_as_many_rows_as_greedy(seed):
    import random

    rng = random.Random(seed)
    # Dense, overlapping amounts and dates force many competing candidates.
    ledger = _random_rows(rng, 300, "I", internal)
    statement = _random_rows(rng, 300, "E", external)
    greedy = _greedy_fuzzy_pairs(ledger, statement)
    optimal = _fuzzy_pairs(run_matching(ledger, statement))
    assert greedy  # the scenario really exercises fuzzy pairing
    assert len(optimal) >= len(greedy)
    assert len(set(optimal.values())) == len(optimal)  # each bank row used once


# ── Phase 3: split settlements ───────────────────────────────────────────────


def test_bank_batch_deposit_is_grouped_with_the_ledger_entries_it_settles():
    ledger = [
        internal("INV-1", "120.10"),
        internal("INV-2", "75.25"),
        internal("INV-3", "301.65", ts=BASE + timedelta(days=1)),
        internal("OTHER", "999.99"),
    ]
    bank = [external("DEP-9", "497.00", ts=BASE + timedelta(days=2))]
    breaks = run_matching(ledger, bank)
    split = next(row for row in breaks if row.break_type == SPLIT_SETTLEMENT)
    assert split.transaction_id == "DEP-9"
    assert split.related_ids == ["INV-1", "INV-2", "INV-3"]
    assert split.internal_amount == split.external_amount == Decimal("497.00")
    assert split.evidence_side == "many_internal"
    assert split.confidence == MEDIUM
    # Only the unrelated row is left over; the three members are accounted for.
    assert [(row.transaction_id, row.break_type) for row in breaks if row is not split] == [
        ("OTHER", MISSING_EXTERNAL)
    ]


def test_ledger_entry_paid_in_instalments_is_grouped():
    breaks = run_matching(
        [internal("INV-7", "1000.00", currency="EUR")],
        [
            external("PAY-A", "400.00"),
            external("PAY-B", "600.00", ts=BASE + timedelta(days=3)),
        ],
    )
    assert types_of(breaks) == [SPLIT_SETTLEMENT]
    assert breaks[0].transaction_id == "INV-7"
    assert breaks[0].related_ids == ["PAY-A", "PAY-B"]
    assert breaks[0].evidence_side == "many_external"
    assert breaks[0].currency == "EUR"


def test_split_needs_an_exact_sum_inside_the_date_window():
    near_miss = run_matching(
        [internal("A", "100.00"), internal("B", "50.00")], [external("D", "150.01")]
    )
    assert SPLIT_SETTLEMENT not in types_of(near_miss)
    too_late = run_matching(
        [internal("A", "100.00"), internal("B", "50.00", ts=BASE + timedelta(days=5))],
        [external("D", "150.00")],
    )
    assert SPLIT_SETTLEMENT not in types_of(too_late)


def test_split_does_not_mix_ledger_currencies_or_signs():
    mixed = run_matching(
        [internal("A", "100.00", currency="EUR"), internal("B", "50.00", currency="GBP")],
        [external("D", "150.00")],
    )
    assert SPLIT_SETTLEMENT not in types_of(mixed)
    signs = run_matching(
        [internal("A", "200.00"), internal("B", "-50.00")], [external("D", "150.00")]
    )
    assert SPLIT_SETTLEMENT not in types_of(signs)


def test_split_prefers_fewest_parts_and_flags_ambiguity():
    ledger = [internal(name, amount) for name, amount in [("A", "10"), ("B", "20"), ("C", "30")]]
    fewest = run_matching(ledger + [internal("D", "40")], [external("X", "60")])
    split = next(row for row in fewest if row.break_type == SPLIT_SETTLEMENT)
    assert split.related_ids == ["B", "D"]  # two parts beat A + B + C
    ambiguous = run_matching(
        ledger + [internal("E", "40"), internal("F", "50")], [external("X", "60")]
    )
    split = next(row for row in ambiguous if row.break_type == SPLIT_SETTLEMENT)
    assert split.confidence == LOW
    assert "another combination" in split.description


# ── Confidence and reference mismatches ──────────────────────────────────────


def test_same_amount_same_day_with_a_different_reference_is_a_reference_mismatch():
    breaks = run_matching([internal("INV-1", "250.00")], [external("BNK-77", "250.00")])
    assert types_of(breaks) == [REFERENCE_MISMATCH]
    assert breaks[0].external_transaction_id == "BNK-77"
    assert breaks[0].confidence == HIGH


def test_confidence_drops_when_several_rows_compete():
    contested = run_matching(
        [internal("A", "100.00"), internal("B", "100.10")],
        [external("X", "100.05"), external("Y", "100.12")],
    )
    assert {row.confidence for row in contested} == {LOW}
    assert all(row.confidence in CONFIDENCE_LEVELS for row in contested)


def test_missing_row_with_a_competing_candidate_is_only_medium_confidence():
    breaks = run_matching(
        [internal("A", "100.00"), internal("B", "100.00")], [external("X", "100.00")]
    )
    missing = next(row for row in breaks if row.break_type == MISSING_EXTERNAL)
    assert missing.confidence == MEDIUM
    lonely = run_matching([internal("A", "100.00")], [])[0]
    assert lonely.confidence == HIGH


def test_duplicate_with_a_different_amount_is_flagged_for_a_closer_look():
    breaks = run_matching(
        [internal("T1", "100.00"), internal("T1", "100.00"), internal("T1", "90.00")],
        [external("T1", "100.00")],
    )
    assert [row.confidence for row in breaks if row.break_type == DUPLICATE] == [HIGH, MEDIUM]


def test_fx_suggestions_are_never_high_confidence():
    breaks = run_matching([internal("T1", "100.00", currency="EUR")], [external("T1", "100.03")])
    assert breaks[0].confidence == MEDIUM


def test_fallback_scales_to_upload_limit():
    import time

    # 10,000 rows per side (the upload limit), every ID mangled so all of them
    # go through the fuzzy fallback. A full scan would make 10^8 comparisons.
    ledger = [internal(f"L{i:05d}", Decimal(i) + Decimal("0.10")) for i in range(10_000)]
    statement = [external(f"S{i:05d}", Decimal(i)) for i in range(10_000)]
    started = time.perf_counter()
    breaks = run_matching(ledger, statement)
    assert time.perf_counter() - started < 5
    assert len(breaks) == 10_000
    assert {record.break_type for record in breaks} == {AMOUNT_MISMATCH}


def test_split_search_stays_fast_on_unrelated_files():
    import time

    # Nothing pairs, every row shares one date, and every bank amount is larger
    # than every ledger amount: the worst case for the split search.
    ledger = [internal(f"L{i:05d}", Decimal(i % 997) + Decimal("0.01")) for i in range(10_000)]
    statement = [external(f"S{i:05d}", Decimal(5_000 + i) + Decimal("0.37")) for i in range(10_000)]
    started = time.perf_counter()
    breaks = run_matching(ledger, statement)
    assert time.perf_counter() - started < 10
    assert len(breaks) == 20_000
