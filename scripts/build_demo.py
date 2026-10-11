# ruff: noqa: E402
"""Build a reproducible browser fixture with the actual Python matcher."""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.engine.matcher import (
    load_internal_ledger,
    load_external_statement,
    run_matching,
)
from app.engine.evaluation import compute_metrics


def encode(value):
    if isinstance(value, Decimal):
        return format(value, ".4f")
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(type(value).__name__)


def build_snapshot():
    with tempfile.TemporaryDirectory(prefix="ledger-recon-demo-") as folder:
        directory = Path(folder)
        subprocess.run(
            [sys.executable, str(ROOT / "backend/data/generate_data.py")],
            env={
                **os.environ,
                "RECON_DATA_DIR": folder,
                "RECON_RANDOM_SEED": "42",
                "PYTHONIOENCODING": "utf-8",
            },
            check=True,
            capture_output=True,
        )
        ledger, statement = (
            directory / "internal_ledger.csv",
            directory / "bank_statement.csv",
        )
        internal, external = (
            load_internal_ledger(ledger),
            load_external_statement(statement),
        )
        records = run_matching(internal, external)
        with (directory / "ground_truth.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            truth = {
                (row["transaction_id"], row["break_type"])
                for row in csv.DictReader(handle)
                if row["is_actually_a_break"].lower() == "true"
            }
        items = []
        for record in records:
            item = asdict(record)
            item.update(
                break_id=str(
                    uuid.uuid5(uuid.NAMESPACE_URL, "ledger-recon:" + record.identity)
                ),
                source="synthetic",
                detected_at="2025-01-07T12:00:00Z",
                resolved=False,
                resolved_at=None,
                job_id=None,
                ai_explanation=None,
            )
            items.append(item)
        engine = (ROOT / "backend/app/engine/matcher.py").read_text(
            encoding="utf-8-sig"
        )
        return {
            "version": 1,
            "seed": 42,
            "description": "Precomputed synthetic results from the Python matcher; no live inference",
            "input_fingerprint": hashlib.sha256(
                ledger.read_bytes() + statement.read_bytes()
            ).hexdigest(),
            "engine_fingerprint": hashlib.sha256(engine.encode()).hexdigest(),
            "ledger_rows": len(internal),
            "statement_rows": len(external),
            "evaluation": compute_metrics(
                truth, {(row.transaction_id, row.break_type) for row in records}
            ),
            "items": items,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed demo fixture differs",
    )
    args = parser.parse_args()
    output = ROOT / "frontend/src/demo/snapshot.json"
    snapshot = build_snapshot()
    content = json.dumps(snapshot, default=encode, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not output.exists() or json.loads(
            output.read_text(encoding="utf-8")
        ) != json.loads(content):
            raise SystemExit("Demo fixture is stale. Run python scripts/build_demo.py")
        print("Demo fixture matches the generator and matcher")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8", newline="\n")
        print(
            f"Built demo: {snapshot['ledger_rows']} ledger rows, {len(snapshot['items'])} breaks"
        )
    print(f"Synthetic micro F1: {snapshot['evaluation']['overall']['f1']:.3f}")


if __name__ == "__main__":
    main()
