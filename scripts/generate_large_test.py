"""
Generate large test ledger and statement CSVs with 1000+ transactions
and a variety of planted breaks for demo/interview purposes.
"""
import csv
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os

random.seed(42)

BASE_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)
CURRENCIES = ["USD", "USD", "USD", "USD", "GBP", "EUR", "JPY", "CAD"]
DESCRIPTIONS = [
    "Wire transfer payment", "Vendor invoice settlement", "Payroll disbursement",
    "Supplier payment", "Client refund", "Equipment lease", "Software subscription",
    "Office supplies", "Consulting fee", "Insurance premium", "Tax payment",
    "Utility bill", "Freight charges", "Marketing spend", "Travel reimbursement",
    "Raw material purchase", "License fee", "Maintenance contract", "Bank charges",
    "Dividend payment"
]

def rand_date(start_offset=0, end_offset=180):
    return BASE_DATE + timedelta(days=random.randint(start_offset, end_offset),
                                  hours=random.randint(0, 23),
                                  minutes=random.randint(0, 59))

def rand_amount():
    return round(random.uniform(10.00, 50000.00), 2)

TOTAL = 1000
N_AMOUNT_MISMATCH = 30
N_MISSING_INTERNAL = 20
N_MISSING_EXTERNAL = 20
N_DUPLICATE = 15
N_TIMING_LAG = 20
N_FX_ROUNDING = 15
N_CLEAN = TOTAL - (N_AMOUNT_MISMATCH + N_MISSING_INTERNAL + N_MISSING_EXTERNAL +
                   N_DUPLICATE + N_TIMING_LAG + N_FX_ROUNDING)

ledger_rows = []
statement_rows = []

# ── Clean Matches ──────────────────────────────────────────────────────────────
for i in range(N_CLEAN):
    txn_id = f"TXN-LG-{1000 + i:04d}"
    amt = rand_amount()
    ts = rand_date()
    desc = random.choice(DESCRIPTIONS)
    currency = random.choice(CURRENCIES)
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": amt, "currency": currency,
        "timestamp": ts.isoformat(), "description": desc, "status": "POSTED"
    })
    statement_rows.append({
        "transaction_id": txn_id, "amount": amt,
        "timestamp": ts.isoformat(), "description": desc
    })

# ── Amount Mismatches ─────────────────────────────────────────────────────────
for i in range(N_AMOUNT_MISMATCH):
    txn_id = f"TXN-AM-{i:04d}"
    internal_amt = rand_amount()
    delta = round(random.uniform(1.00, 500.00), 2) * random.choice([-1, 1])
    external_amt = round(internal_amt + delta, 2)
    ts = rand_date()
    desc = random.choice(DESCRIPTIONS)
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": internal_amt, "currency": "USD",
        "timestamp": ts.isoformat(), "description": desc, "status": "POSTED"
    })
    statement_rows.append({
        "transaction_id": txn_id, "amount": external_amt,
        "timestamp": ts.isoformat(), "description": desc
    })

# ── Missing Internal (in bank, not in ledger) ─────────────────────────────────
for i in range(N_MISSING_INTERNAL):
    txn_id = f"TXN-MI-{i:04d}"
    amt = rand_amount()
    ts = rand_date()
    statement_rows.append({
        "transaction_id": txn_id, "amount": amt,
        "timestamp": ts.isoformat(), "description": random.choice(DESCRIPTIONS)
    })

# ── Missing External (in ledger, not in bank) ─────────────────────────────────
for i in range(N_MISSING_EXTERNAL):
    txn_id = f"TXN-ME-{i:04d}"
    amt = rand_amount()
    ts = rand_date()
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": amt, "currency": "USD",
        "timestamp": ts.isoformat(), "description": random.choice(DESCRIPTIONS), "status": "POSTED"
    })

# ── Duplicates ────────────────────────────────────────────────────────────────
for i in range(N_DUPLICATE):
    txn_id = f"TXN-DUP-{i:04d}"
    amt = rand_amount()
    ts = rand_date()
    desc = random.choice(DESCRIPTIONS)
    # Add original to both
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": amt, "currency": "USD",
        "timestamp": ts.isoformat(), "description": desc, "status": "POSTED"
    })
    statement_rows.append({
        "transaction_id": txn_id, "amount": amt,
        "timestamp": ts.isoformat(), "description": desc
    })
    # Add duplicate to internal ledger
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": amt, "currency": "USD",
        "timestamp": ts.isoformat(), "description": f"DUPLICATE: {desc}", "status": "POSTED"
    })

# ── Timing Lags ───────────────────────────────────────────────────────────────
for i in range(N_TIMING_LAG):
    txn_id = f"TXN-TL-{i:04d}"
    amt = rand_amount()
    internal_ts = rand_date(end_offset=170)
    lag_days = random.randint(1, 3)
    external_ts = internal_ts + timedelta(days=lag_days)
    desc = random.choice(DESCRIPTIONS)
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": amt, "currency": "USD",
        "timestamp": internal_ts.isoformat(), "description": desc, "status": "POSTED"
    })
    statement_rows.append({
        "transaction_id": txn_id, "amount": amt,
        "timestamp": external_ts.isoformat(), "description": desc
    })

# ── FX Rounding ───────────────────────────────────────────────────────────────
for i in range(N_FX_ROUNDING):
    txn_id = f"TXN-FX-{i:04d}"
    internal_amt = rand_amount()
    fx_noise = round(random.uniform(0.001, 0.049), 4)
    external_amt = round(internal_amt + fx_noise, 4)
    ts = rand_date()
    desc = random.choice(DESCRIPTIONS)
    currency = random.choice(["GBP", "EUR", "CAD", "JPY"])
    ledger_rows.append({
        "transaction_id": txn_id, "account_id": f"ACC-{random.randint(100,999)}",
        "amount": internal_amt, "currency": currency,
        "timestamp": ts.isoformat(), "description": desc, "status": "POSTED"
    })
    statement_rows.append({
        "transaction_id": txn_id, "amount": external_amt,
        "timestamp": ts.isoformat(), "description": desc
    })

# ── Shuffle ───────────────────────────────────────────────────────────────────
random.shuffle(ledger_rows)
random.shuffle(statement_rows)

# ── Write ─────────────────────────────────────────────────────────────────────
out_dir = os.path.dirname(os.path.abspath(__file__))

ledger_path = os.path.join(out_dir, "large_test_ledger.csv")
with open(ledger_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["transaction_id","account_id","amount","currency","timestamp","description","status"])
    writer.writeheader()
    writer.writerows(ledger_rows)

statement_path = os.path.join(out_dir, "large_test_statement.csv")
with open(statement_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["transaction_id","amount","timestamp","description"])
    writer.writeheader()
    writer.writerows(statement_rows)

print(f"Done!")
print(f"Ledger rows  : {len(ledger_rows)} -> {ledger_path}")
print(f"Statement rows: {len(statement_rows)} -> {statement_path}")
print(f"\nPlanted breaks summary:")
print(f"  Clean matches    : {N_CLEAN}")
print(f"  Amount mismatch  : {N_AMOUNT_MISMATCH}")
print(f"  Missing internal : {N_MISSING_INTERNAL}")
print(f"  Missing external : {N_MISSING_EXTERNAL}")
print(f"  Duplicates       : {N_DUPLICATE}")
print(f"  Timing lags      : {N_TIMING_LAG}")
print(f"  FX rounding      : {N_FX_ROUNDING}")
print(f"  TOTAL breaks     : {N_AMOUNT_MISMATCH+N_MISSING_INTERNAL+N_MISSING_EXTERNAL+N_DUPLICATE+N_TIMING_LAG+N_FX_ROUNDING}")
