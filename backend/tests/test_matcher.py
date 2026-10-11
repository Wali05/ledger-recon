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
    DUPLICATE,
    FX_ROUNDING,
    MISSING_EXTERNAL,
    MISSING_INTERNAL,
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
