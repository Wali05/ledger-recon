"""
Synthetic Data Generator for the Ledger Reconciliation Engine.

METHODOLOGY:
  - Generates 5,000 "clean" matching transactions (same transaction_id in both feeds).
  - Then deliberately plants break-inducing rows across the two feeds.
  - A ground_truth.csv is written that labels every planted break with its break_type.

GROUND TRUTH INTEGRITY NOTE:
  The ground truth is assigned at GENERATION TIME — we know exactly which transaction_ids
  we planted and what kind of break we introduced. The ground truth is NOT derived from
  the same features (amount delta, date delta) that the matching engine later uses to
  detect breaks. This avoids the circular evaluation trap where a detection heuristic
  appears to have perfect recall simply because the ground truth was derived from the
  same signal. The ground truth here is an external oracle: we assigned it, we know it.

FX_ROUNDING ANTI-CIRCULARITY DESIGN:
  The initial version of this generator used a detector-mirror design: FX breaks were
  always planted with delta in [0.01, 0.04] and a non-USD currency — exactly the
  conditions the matcher checks. This produced a perfect 1.0 F1 that reflected circular
  design, not real generalisation.

  Three noise categories are now added to break that circularity:

  FX_FP_CANDIDATES (5 rows, GT=AMOUNT_MISMATCH):
    Non-USD currency, delta in [0.01, 0.04] — indistinguishable by the detector from
    real FX rounding, but the ground truth says these are genuine small fees (not FX).
    These will be false-positively classified as FX_ROUNDING by the engine, reducing
    FX_ROUNDING precision and AMOUNT_MISMATCH recall.

  FX_LARGE_DELTA (5 rows, GT=FX_ROUNDING):
    Non-USD currency, delta in [0.08, 0.35] — legitimate FX rounding on a large amount
    where the conversion swing exceeded the $0.05 threshold. The engine will call these
    AMOUNT_MISMATCH because delta > $0.05. Reduces FX_ROUNDING recall.

  FX_USD_NORMALISED (5 rows, GT=FX_ROUNDING):
    The internal system recorded currency='USD' (normalised at booking) even though the
    transaction was a foreign-currency transfer. The engine cannot detect these as FX
    because the currency flag is lost — it sees (USD, delta <= $0.05) and returns
    AMOUNT_MISMATCH. Reduces FX_ROUNDING recall.

  Together these three noise categories mean the engine will produce:
    - FP > 0 for FX_ROUNDING (the FP candidates)
    - FN > 0 for FX_ROUNDING (the large-delta and USD-normalised cases)
  So the reported F1 will be < 1.0, which is an honest estimate.

PLANTED BREAKS (exact counts, after noise addition):
  Core planted breaks:
  - AMOUNT_MISMATCH        : 40  (fee deduction, always USD, delta $0.50-$2.50)
  - MISSING_INTERNAL       : 15  (in external only)
  - MISSING_EXTERNAL       : 15  (in internal only)
  - DUPLICATE              : 20  (appears twice in external feed)
  - TIMING_LAG             : 15  (date shifted 1-3 days)
  - FX_ROUNDING (detectable): 10  (non-USD, delta <= $0.05 — engine CAN detect these)

  FX noise breaks (total 15):
  - FX_FP_CANDIDATES       :  5  (GT=AMOUNT_MISMATCH, but engine classifies FX_ROUNDING)
  - FX_LARGE_DELTA         :  5  (GT=FX_ROUNDING, but engine classifies AMOUNT_MISMATCH)
  - FX_USD_NORMALISED      :  5  (GT=FX_ROUNDING, but engine classifies AMOUNT_MISMATCH)

  Total FX_ROUNDING in ground truth: 10 + 5 + 5 = 20
  Total AMOUNT_MISMATCH in ground truth: 40 + 5 = 45
  Grand total planted: 115 + 15 = 130
"""

import csv
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Reproducibility ────────────────────────────────────────────────────────
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ── Configuration ─────────────────────────────────────────────────────────
NUM_CLEAN = 5_000
NUM_AMOUNT_MISMATCH = 40
NUM_MISSING_INTERNAL = 15  # in external, missing from internal
NUM_MISSING_EXTERNAL = 15  # in internal, missing from external
NUM_DUPLICATE = 20         # same txn_id appears twice in one feed
NUM_TIMING_LAG = 15
NUM_FX_ROUNDING = 10       # detectable FX: non-USD, delta <= $0.05
# FX noise — these break the circular evaluation
NUM_FX_FP_CANDIDATES = 5   # GT=AMOUNT_MISMATCH, but engine sees non-USD+small-delta → FP for FX_ROUNDING
NUM_FX_LARGE_DELTA = 5     # GT=FX_ROUNDING, delta > $0.05 → engine calls AMOUNT_MISMATCH → FN
NUM_FX_USD_NORMALISED = 5  # GT=FX_ROUNDING, but internal stored USD → engine calls AMOUNT_MISMATCH → FN

BASE_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD"]
ACCOUNTS = [f"ACC{i:04d}" for i in range(1, 101)]

OUTPUT_DIR = Path(__file__).parent


def random_date(start: datetime, days: int = 365) -> datetime:
    """Return a random datetime within 'days' of start."""
    delta = timedelta(seconds=random.randint(0, days * 86400))
    return start + delta


def random_amount() -> float:
    """Return a realistic transaction amount (2 dp)."""
    return round(random.uniform(10.00, 50_000.00), 2)


def make_transaction_id() -> str:
    return f"TXN-{uuid.uuid4().hex[:12].upper()}"


def description_for(amount: float, account: str) -> str:
    templates = [
        f"Payment from {account}",
        f"Wire transfer {account}",
        f"ACH credit {account}",
        f"Settlement {account}",
        f"Deposit ref {account}",
    ]
    return random.choice(templates)


# ═══════════════════════════════════════════════════════════════════
# Step 1 — Generate 5,000 clean matching transactions
# ═══════════════════════════════════════════════════════════════════

print("Generating 5,000 clean matching transactions...")

clean_txns = []
for _ in range(NUM_CLEAN):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    amount = random_amount()
    ts = random_date(BASE_DATE)
    desc = description_for(amount, account)
    currency = "USD"  # clean txns always USD for simplicity
    clean_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "amount": amount,
        "currency": currency,
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })

# ═══════════════════════════════════════════════════════════════════
# Step 2 — Generate planted break transactions
# ═══════════════════════════════════════════════════════════════════

ground_truth = []  # list of {transaction_id, break_type, is_actually_a_break}

# ── AMOUNT_MISMATCH ──────────────────────────────────────────────
print(f"Planting {NUM_AMOUNT_MISMATCH} AMOUNT_MISMATCH breaks...")
amount_mismatch_txns = []
for _ in range(NUM_AMOUNT_MISMATCH):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    internal_amount = random_amount()
    # External amount differs by a small fee/rounding error (not FX — always USD)
    fee = round(random.uniform(0.50, 2.50), 2)
    external_amount = round(internal_amount - fee, 2)  # bank deducted a fee
    ts = random_date(BASE_DATE)
    desc = description_for(internal_amount, account)
    amount_mismatch_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "internal_amount": internal_amount,
        "external_amount": external_amount,
        "currency": "USD",
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "AMOUNT_MISMATCH",
        "is_actually_a_break": True,
    })

# ── MISSING_INTERNAL (in external, not in internal) ──────────────
print(f"Planting {NUM_MISSING_INTERNAL} MISSING_INTERNAL breaks...")
missing_internal_txns = []
for _ in range(NUM_MISSING_INTERNAL):
    txn_id = make_transaction_id()
    amount = random_amount()
    ts = random_date(BASE_DATE)
    desc = f"Unrecognised credit {txn_id[:8]}"
    missing_internal_txns.append({
        "transaction_id": txn_id,
        "amount": round(amount, 2),
        "timestamp": ts.isoformat(),
        "description": desc,
    })
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "MISSING_INTERNAL",
        "is_actually_a_break": True,
    })

# ── MISSING_EXTERNAL (in internal, not in external) ──────────────
print(f"Planting {NUM_MISSING_EXTERNAL} MISSING_EXTERNAL breaks...")
missing_external_txns = []
for _ in range(NUM_MISSING_EXTERNAL):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    amount = random_amount()
    ts = random_date(BASE_DATE)
    desc = description_for(amount, account)
    missing_external_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "amount": round(amount, 2),
        "currency": "USD",
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "pending",  # common reason for missing from bank: not yet settled
    })
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "MISSING_EXTERNAL",
        "is_actually_a_break": True,
    })

# ── DUPLICATE ────────────────────────────────────────────────────
# Strategy: create 20 txns that appear TWICE in the EXTERNAL feed.
# The internal ledger has them once (as normal). The external duplicate
# simulates a bank re-processing a transaction twice.
print(f"Planting {NUM_DUPLICATE} DUPLICATE breaks...")
duplicate_txns = []
for _ in range(NUM_DUPLICATE):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    amount = random_amount()
    ts = random_date(BASE_DATE)
    desc = description_for(amount, account)
    duplicate_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "amount": round(amount, 2),
        "currency": "USD",
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "DUPLICATE",
        "is_actually_a_break": True,
    })

# ── TIMING_LAG ───────────────────────────────────────────────────
# Same amount/ID, but external date is 1-3 days later (settlement lag).
print(f"Planting {NUM_TIMING_LAG} TIMING_LAG breaks...")
timing_lag_txns = []
for _ in range(NUM_TIMING_LAG):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    amount = random_amount()
    internal_ts = random_date(BASE_DATE, days=300)
    lag_days = random.randint(1, 3)
    external_ts = internal_ts + timedelta(days=lag_days)
    desc = description_for(amount, account)
    timing_lag_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "amount": round(amount, 2),
        "currency": "USD",
        "internal_timestamp": internal_ts.isoformat(),
        "external_timestamp": external_ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "TIMING_LAG",
        "is_actually_a_break": True,
    })

# ── FX_ROUNDING (detectable) ─────────────────────────────────────
# Non-USD, delta <= $0.05. The engine CAN detect these correctly.
print(f"Planting {NUM_FX_ROUNDING} detectable FX_ROUNDING breaks...")
fx_rounding_txns = []
fx_currencies = ["EUR", "GBP", "CAD"]
for _ in range(NUM_FX_ROUNDING):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    base_amount = random_amount()
    currency = random.choice(fx_currencies)
    fx_delta = round(random.uniform(0.01, 0.04), 4)
    external_amount = round(base_amount + fx_delta, 2)
    ts = random_date(BASE_DATE)
    desc = f"FX transfer {currency} {account}"
    fx_rounding_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "internal_amount": round(base_amount, 2),
        "external_amount": round(external_amount, 2),
        "currency": currency,
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "FX_ROUNDING",
        "is_actually_a_break": True,
    })

# ── FX NOISE 1: False-positive candidates (GT=AMOUNT_MISMATCH) ───
# Non-USD currency, delta in [0.01, 0.04] — detector cannot distinguish these
# from real FX rounding (same features). But the ground truth says they are
# genuine small fees, NOT FX. Engine will label them FX_ROUNDING → false positive.
# This tests: does the detector over-classify FX_ROUNDING on non-USD rows?
print(f"Planting {NUM_FX_FP_CANDIDATES} FX false-positive candidates (GT=AMOUNT_MISMATCH)...")
fx_fp_txns = []
for _ in range(NUM_FX_FP_CANDIDATES):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    base_amount = random_amount()
    currency = random.choice(fx_currencies)  # non-USD, same as real FX
    # Small delta — same range as real FX rows, but this is actually a fee
    fee = round(random.uniform(0.01, 0.04), 4)
    external_amount = round(base_amount - fee, 2)  # fee deducted
    ts = random_date(BASE_DATE)
    desc = f"Intl wire fee {currency} {account}"
    fx_fp_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "internal_amount": round(base_amount, 2),
        "external_amount": round(external_amount, 2),
        "currency": currency,
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    # Ground truth: this IS a break, but it's an AMOUNT_MISMATCH (a real fee),
    # not FX_ROUNDING. The engine will get this WRONG.
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "AMOUNT_MISMATCH",
        "is_actually_a_break": True,
    })

# ── FX NOISE 2: Large-delta FX (GT=FX_ROUNDING, engine misses) ───
# Genuine FX rounding on a volatile currency day — delta exceeds the $0.05
# threshold. Ground truth: FX_ROUNDING. Engine sees delta > $0.05 → AMOUNT_MISMATCH.
# This tests the threshold's recall ceiling.
print(f"Planting {NUM_FX_LARGE_DELTA} large-delta FX_ROUNDING breaks (engine will miss)...")
fx_large_txns = []
for _ in range(NUM_FX_LARGE_DELTA):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    base_amount = random_amount()
    currency = random.choice(fx_currencies)  # non-USD
    # Delta exceeds the $0.05 threshold — real FX swing on a volatile day
    fx_delta = round(random.uniform(0.08, 0.35), 4)
    external_amount = round(base_amount + fx_delta, 2)
    ts = random_date(BASE_DATE)
    desc = f"FX wire large swing {currency} {account}"
    fx_large_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "internal_amount": round(base_amount, 2),
        "external_amount": round(external_amount, 2),
        "currency": currency,
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    # Ground truth: FX_ROUNDING (the root cause is FX). Engine: AMOUNT_MISMATCH → FN.
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "FX_ROUNDING",
        "is_actually_a_break": True,
    })

# ── FX NOISE 3: USD-normalised FX (GT=FX_ROUNDING, engine misses) ──
# The internal system normalised the booking currency to USD (common in core banking
# systems that run a USD ledger regardless of origination currency). The FX delta
# is still there, but the currency flag is USD. Engine: sees (USD, small delta) →
# AMOUNT_MISMATCH. Ground truth: FX_ROUNDING. This is the documented limitation.
print(f"Planting {NUM_FX_USD_NORMALISED} USD-normalised FX breaks (GT=FX_ROUNDING, engine misses)...")
fx_usd_norm_txns = []
for _ in range(NUM_FX_USD_NORMALISED):
    txn_id = make_transaction_id()
    account = random.choice(ACCOUNTS)
    base_amount = random_amount()
    # currency stored as USD even though underlying was foreign
    fx_delta = round(random.uniform(0.01, 0.04), 4)
    external_amount = round(base_amount + fx_delta, 2)
    ts = random_date(BASE_DATE)
    desc = f"USD normalised FX booking {account}"
    fx_usd_norm_txns.append({
        "transaction_id": txn_id,
        "account_id": account,
        "internal_amount": round(base_amount, 2),
        "external_amount": round(external_amount, 2),
        "currency": "USD",  # <- normalised — the currency information is LOST
        "timestamp": ts.isoformat(),
        "description": desc,
        "status": "settled",
    })
    # Ground truth: FX_ROUNDING (underlying cause). Engine: AMOUNT_MISMATCH → FN.
    ground_truth.append({
        "transaction_id": txn_id,
        "break_type": "FX_ROUNDING",
        "is_actually_a_break": True,
    })

# ── Mark clean transactions as non-breaks in ground truth ────────
for txn in clean_txns:
    ground_truth.append({
        "transaction_id": txn["transaction_id"],
        "break_type": "NONE",
        "is_actually_a_break": False,
    })


# ═══════════════════════════════════════════════════════════════════
# Step 3 — Assemble the two feeds
# ═══════════════════════════════════════════════════════════════════

# INTERNAL LEDGER rows
internal_rows = []

# Clean transactions
for txn in clean_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["amount"],
        "currency": txn["currency"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# Amount mismatch: internal has the "true" amount
for txn in amount_mismatch_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["internal_amount"],
        "currency": txn["currency"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# Missing external: internal has these, external does not
for txn in missing_external_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["amount"],
        "currency": txn["currency"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# Duplicates: internal has ONE copy (the bank duplicated it)
for txn in duplicate_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["amount"],
        "currency": txn["currency"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# Timing lag: internal has the earlier timestamp
for txn in timing_lag_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["amount"],
        "currency": txn["currency"],
        "timestamp": txn["internal_timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# FX rounding: internal has non-USD amount
for txn in fx_rounding_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["internal_amount"],
        "currency": txn["currency"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# FX noise 1: false-positive candidates (non-USD, small delta, but GT=AMOUNT_MISMATCH)
for txn in fx_fp_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["internal_amount"],
        "currency": txn["currency"],  # non-USD
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# FX noise 2: large-delta FX (non-USD, delta > $0.05, GT=FX_ROUNDING)
for txn in fx_large_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["internal_amount"],
        "currency": txn["currency"],  # non-USD
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# FX noise 3: USD-normalised FX (currency='USD', small delta, GT=FX_ROUNDING)
for txn in fx_usd_norm_txns:
    internal_rows.append({
        "transaction_id": txn["transaction_id"],
        "account_id": txn["account_id"],
        "amount": txn["internal_amount"],
        "currency": txn["currency"],  # 'USD' — currency flag lost
        "timestamp": txn["timestamp"],
        "description": txn["description"],
        "status": txn["status"],
    })

# Shuffle internal rows so planted breaks aren't contiguous
random.shuffle(internal_rows)

# EXTERNAL BANK STATEMENT rows
external_rows = []

# Clean transactions
for txn in clean_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# Amount mismatch: external has the different (fee-deducted) amount
for txn in amount_mismatch_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["external_amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# Missing internal: external has these, internal does not
for txn in missing_internal_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# Duplicates: external has TWO copies (bank re-processed)
for txn in duplicate_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })
    # Second (duplicate) copy
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# Timing lag: external has the later timestamp
for txn in timing_lag_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["amount"],
        "timestamp": txn["external_timestamp"],
        "description": txn["description"],
    })

# FX rounding: external has USD amount (slightly different due to FX)
for txn in fx_rounding_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["external_amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# FX noise 1: false-positive candidates (external shows fee-reduced amount)
for txn in fx_fp_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["external_amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# FX noise 2: large-delta FX (external shows USD-converted amount)
for txn in fx_large_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["external_amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# FX noise 3: USD-normalised FX (external shows converted amount)
for txn in fx_usd_norm_txns:
    external_rows.append({
        "transaction_id": txn["transaction_id"],
        "amount": txn["external_amount"],
        "timestamp": txn["timestamp"],
        "description": txn["description"],
    })

# Shuffle external rows
random.shuffle(external_rows)


# ═══════════════════════════════════════════════════════════════════
# Step 4 — Write output files
# ═══════════════════════════════════════════════════════════════════

# Internal ledger → loaded into PostgreSQL via the load_ledger.py script
internal_path = OUTPUT_DIR / "internal_ledger.csv"
with open(internal_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "transaction_id", "account_id", "amount", "currency",
        "timestamp", "description", "status",
    ])
    writer.writeheader()
    writer.writerows(internal_rows)
print(f"[OK] internal_ledger.csv written: {len(internal_rows)} rows")

# External bank statement → simulates the CSV from the bank
external_path = OUTPUT_DIR / "bank_statement.csv"
with open(external_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "transaction_id", "amount", "timestamp", "description",
    ])
    writer.writeheader()
    writer.writerows(external_rows)
print(f"[OK] bank_statement.csv written: {len(external_rows)} rows")

# Ground truth — the external oracle for evaluation
gt_path = OUTPUT_DIR / "ground_truth.csv"
with open(gt_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "transaction_id", "break_type", "is_actually_a_break",
    ])
    writer.writeheader()
    writer.writerows(ground_truth)
print(f"[OK] ground_truth.csv written: {len(ground_truth)} rows")

# Summary JSON for reference
summary = {
    "random_seed": RANDOM_SEED,
    "clean_transactions": NUM_CLEAN,
    "planted_breaks": {
        "AMOUNT_MISMATCH_core": NUM_AMOUNT_MISMATCH,
        "AMOUNT_MISMATCH_fx_fp_candidates": NUM_FX_FP_CANDIDATES,
        "AMOUNT_MISMATCH_total_in_gt": NUM_AMOUNT_MISMATCH + NUM_FX_FP_CANDIDATES,
        "MISSING_INTERNAL": NUM_MISSING_INTERNAL,
        "MISSING_EXTERNAL": NUM_MISSING_EXTERNAL,
        "DUPLICATE": NUM_DUPLICATE,
        "TIMING_LAG": NUM_TIMING_LAG,
        "FX_ROUNDING_detectable": NUM_FX_ROUNDING,
        "FX_ROUNDING_large_delta_fn": NUM_FX_LARGE_DELTA,
        "FX_ROUNDING_usd_normalised_fn": NUM_FX_USD_NORMALISED,
        "FX_ROUNDING_total_in_gt": NUM_FX_ROUNDING + NUM_FX_LARGE_DELTA + NUM_FX_USD_NORMALISED,
    },
    "total_planted": (
        NUM_AMOUNT_MISMATCH + NUM_FX_FP_CANDIDATES
        + NUM_MISSING_INTERNAL + NUM_MISSING_EXTERNAL
        + NUM_DUPLICATE + NUM_TIMING_LAG
        + NUM_FX_ROUNDING + NUM_FX_LARGE_DELTA + NUM_FX_USD_NORMALISED
    ),
    "internal_ledger_rows": len(internal_rows),
    "external_statement_rows": len(external_rows),
    "ground_truth_rows": len(ground_truth),
    "note": "FX_FP_CANDIDATES are GT=AMOUNT_MISMATCH but engine predicts FX_ROUNDING (FP). "
            "FX_LARGE_DELTA and FX_USD_NORMALISED are GT=FX_ROUNDING but engine predicts AMOUNT_MISMATCH (FN).",
}
summary_path = OUTPUT_DIR / "generation_summary.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)
print(f"[OK] generation_summary.json written")
print("\nSummary:")
for k, v in summary.items():
    print(f"  {k}: {v}")


