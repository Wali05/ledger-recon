#!/usr/bin/env python3
"""
Local development startup helper.

This script tests the matching engine logic LOCALLY without needing Docker/PostgreSQL/Redis.
It runs the matching engine directly against the generated CSV files and prints a summary
of detected breaks — useful for developing and testing the engine logic in isolation.

For the full stack (API + Celery + DB), use Docker Compose.
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

DATA_DIR = Path(__file__).parent / "backend" / "data"

from app.engine.matcher import load_internal_ledger, load_external_statement, run_matching
from collections import Counter

print("=" * 60)
print("  LEDGER RECONCILIATION ENGINE — LOCAL SMOKE TEST")
print("=" * 60)

internal_path = DATA_DIR / "internal_ledger.csv"
external_path = DATA_DIR / "bank_statement.csv"

if not internal_path.exists():
    print(f"ERROR: {internal_path} not found. Run backend/data/generate_data.py first.")
    sys.exit(1)

print(f"\nLoading internal ledger from {internal_path.name}...")
internal = load_internal_ledger(internal_path)
print(f"  {len(internal)} rows loaded")

print(f"Loading external statement from {external_path.name}...")
external = load_external_statement(external_path)
print(f"  {len(external)} rows loaded")

print("\nRunning matching engine...")
breaks = run_matching(internal, external)

print(f"\nDetected {len(breaks)} breaks:")
counts = Counter(b.break_type for b in breaks)
for bt, count in sorted(counts.items()):
    print(f"  {bt:<20} {count}")

print("\nExpected planted breaks:")
print("  AMOUNT_MISMATCH      40")
print("  MISSING_INTERNAL     15")
print("  MISSING_EXTERNAL     15")
print("  DUPLICATE            20")
print("  TIMING_LAG           15")
print("  FX_ROUNDING          10")
print("  TOTAL                115")
print()
print("NOTE: Counts may vary from expected due to edge cases.")
print("      Run evaluate.py for full precision/recall analysis.")
print("=" * 60)
