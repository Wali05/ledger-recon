# ruff: noqa: E402
"""Evaluate synthetic transaction/type labels without a database."""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.engine.evaluation import compute_metrics
from app.engine.matcher import (
    load_internal_ledger,
    load_external_statement,
    run_matching,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, help="Use an existing labelled fixture directory"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.data_dir is None:
        from build_demo import build_snapshot

        result = build_snapshot()["evaluation"]
    else:
        path = args.data_dir / "ground_truth.csv"
        if not path.exists():
            parser.error("The fixture directory needs ground_truth.csv")
        with path.open(newline="", encoding="utf-8-sig") as handle:
            truth = {
                (row["transaction_id"], row["break_type"])
                for row in csv.DictReader(handle)
                if row["is_actually_a_break"].lower() == "true"
            }
        records = run_matching(
            load_internal_ledger(args.data_dir / "internal_ledger.csv"),
            load_external_statement(args.data_dir / "bank_statement.csv"),
        )
        result = compute_metrics(
            truth, {(row.transaction_id, row.break_type) for row in records}
        )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"{'Break type':<22} {'GT':>4} {'Pred':>4} {'TP':>4} {'FP':>4} {'FN':>4} {'P':>7} {'R':>7} {'F1':>7}"
        )
        for kind, row in result["by_type"].items():
            print(
                f"{kind:<22} {row['gt']:>4} {row['pred']:>4} {row['tp']:>4} {row['fp']:>4} {row['fn']:>4} "
                f"{row['precision']:>7.3f} {row['recall']:>7.3f} {row['f1']:>7.3f}"
            )
        print(f"Overall micro F1: {result['overall']['f1']:.3f}")
        print(
            "Synthetic rule benchmark; repeated duplicate occurrences count once per transaction/type."
        )


if __name__ == "__main__":
    main()
