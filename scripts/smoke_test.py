# ruff: noqa: E402
"""Print actual discrepancy counts from the bundled feeds, without a database."""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.engine.matcher import (
    load_internal_ledger,
    load_external_statement,
    run_matching,
)

internal = load_internal_ledger(ROOT / "backend/data/internal_ledger.csv")
external = load_external_statement(ROOT / "backend/data/bank_statement.csv")
records = run_matching(internal, external)
print(
    f"{len(internal)} ledger rows / {len(external)} statement rows / {len(records)} breaks"
)
for kind, count in sorted(Counter(row.break_type for row in records).items()):
    print(f"{kind:<22} {count}")
