"""
Evaluation Script — Per-Break-Type Precision and Recall.

METHODOLOGY:
  1. Load ground_truth.csv (planted labels, assigned at generation time — NOT derived
     from the same features the matcher uses).
  2. Query reconciliation_breaks from PostgreSQL (the engine's predictions).
  3. For each break_type, compute:
       TP = predicted this type AND ground truth says this type (correct detection)
       FP = predicted this type BUT ground truth says it's a different type or no break
       FN = ground truth says this type BUT engine did NOT detect it (missed)
       Precision = TP / (TP + FP)
       Recall    = TP / (TP + FN)
       F1        = 2 * P * R / (P + R)
  4. Print a formatted per-type table.
  5. Print honest, named commentary on each break type's expected weak spots.

IMPORTANT: precision/recall is computed AT THE TRANSACTION_ID LEVEL, not at the
row level. This is the correct unit of analysis for reconciliation — we care about
whether each transaction's discrepancy was correctly identified.
"""

import csv
import os
import sys
from pathlib import Path
from collections import defaultdict

import psycopg2
from tabulate import tabulate

DATA_DIR = Path(__file__).parent
DB_URL = os.getenv(
    "SYNC_DATABASE_URL",
    "postgresql://recon_user:recon_pass@localhost:5432/ledger_recon",
)

BREAK_TYPES = [
    "AMOUNT_MISMATCH",
    "MISSING_INTERNAL",
    "MISSING_EXTERNAL",
    "DUPLICATE",
    "TIMING_LAG",
    "FX_ROUNDING",
]

LIMITATIONS = {
    "AMOUNT_MISMATCH": (
        "Uses a fixed $0.50 fuzzy amount tolerance. Transactions with matching IDs and "
        "amount delta > $0.05 but ≤ $0.50 may be misclassified as FX_ROUNDING if the "
        "internal currency is non-USD. Inversely, genuine FX rounding with delta > $0.05 "
        "will be promoted to AMOUNT_MISMATCH."
    ),
    "MISSING_INTERNAL": (
        "Detection is straightforward — rows present in external but absent from internal. "
        "Risk of false negatives if the external statement has a different transaction_id "
        "format for the same underlying transaction (Phase 2 fuzzy match might absorb it)."
    ),
    "MISSING_EXTERNAL": (
        "Same logic as MISSING_INTERNAL, mirrored. Low false-positive risk. "
        "Pending transactions (status='pending' in ledger) legitimately absent from bank "
        "feed will generate false positives in production."
    ),
    "DUPLICATE": (
        "Detected by counting transaction_id frequency within each feed before matching. "
        "Near-perfect on synthetic data. In production, banks sometimes use different "
        "transaction_ids for re-presentments, which this engine cannot detect without "
        "additional reference data."
    ),
    "TIMING_LAG": (
        "Fixed 3-day window for date tolerance. In practice, settlement lag can exceed "
        "3 days for international wires or weekends/holidays. The 3-day window was chosen "
        "conservatively to avoid false-positiving on genuinely different transactions. "
        "Larger windows increase recall but reduce precision."
    ),
    "FX_ROUNDING": (
        "Depends on the internal ledger storing a non-USD currency flag. If the internal "
        "system normalises all amounts to USD at booking time, the currency field will be "
        "USD and these will be misclassified as AMOUNT_MISMATCH. The $0.05 threshold is "
        "fixed, not adaptive — legitimate FX swings on large transactions can exceed this "
        "threshold and be missed, while very small genuine amount mismatches on non-USD "
        "transactions may be falsely classified as FX_ROUNDING."
    ),
}


def load_ground_truth(path: Path) -> dict:
    """
    Returns dict: {transaction_id: break_type or None}
    Only includes rows where is_actually_a_break == True.
    """
    gt = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["is_actually_a_break"].lower() == "true":
                gt[row["transaction_id"]] = row["break_type"]
    return gt


def load_engine_predictions(db_url: str) -> dict:
    """
    Returns dict: {transaction_id: break_type}
    Queries the reconciliation_breaks table.
    """
    predictions = {}
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT transaction_id, break_type FROM reconciliation_breaks"
        )
        for txn_id, break_type in cur.fetchall():
            # If the same transaction_id has multiple break records (shouldn't happen
            # due to UNIQUE constraint, but defensive), last one wins
            predictions[txn_id] = break_type
    finally:
        conn.close()
    return predictions


def compute_metrics(ground_truth: dict, predictions: dict) -> dict:
    """
    Compute per-type TP, FP, FN, precision, recall, F1.
    
    Ground truth = planted breaks (what WE know is wrong).
    Predictions  = what the engine detected.
    
    Matching rule: a prediction counts as a TP for type T if:
      - The transaction_id is in ground truth with type T
      - AND the engine predicted type T for that same transaction_id
    """
    metrics = {}
    for bt in BREAK_TYPES:
        # Ground truth positives for this type
        gt_positives = {tid for tid, t in ground_truth.items() if t == bt}
        # Engine predictions for this type
        pred_positives = {tid for tid, t in predictions.items() if t == bt}

        tp = len(gt_positives & pred_positives)
        fp = len(pred_positives - gt_positives)
        fn = len(gt_positives - pred_positives)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        metrics[bt] = {
            "gt_count": len(gt_positives),
            "pred_count": len(pred_positives),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return metrics


def print_report(metrics: dict):
    headers = [
        "Break Type", "GT Count", "Pred Count",
        "TP", "FP", "FN",
        "Precision", "Recall", "F1",
    ]
    rows = []
    for bt, m in metrics.items():
        rows.append([
            bt,
            m["gt_count"],
            m["pred_count"],
            m["tp"],
            m["fp"],
            m["fn"],
            f"{m['precision']:.3f}",
            f"{m['recall']:.3f}",
            f"{m['f1']:.3f}",
        ])

    print("\n" + "═" * 80)
    print("  LEDGER RECONCILIATION ENGINE — EVALUATION REPORT")
    print("═" * 80)
    print(tabulate(rows, headers=headers, tablefmt="grid"))

    print("\n── PER-TYPE ANALYSIS ──────────────────────────────────────────────────────\n")
    for bt, m in metrics.items():
        rating = "✓ GOOD" if m["f1"] >= 0.85 else ("⚠ ACCEPTABLE" if m["f1"] >= 0.60 else "✗ WEAK")
        print(f"{bt}  [{rating}]")
        print(f"  Precision {m['precision']:.3f} | Recall {m['recall']:.3f} | F1 {m['f1']:.3f}")
        print(f"  Limitation: {LIMITATIONS[bt]}")
        print()

    # Overall summary
    all_gt = set()
    all_pred = set()
    gt_dict, pred_dict = {}, {}
    # We need the raw dicts for overall — recompute from metrics is sufficient here
    total_tp = sum(m["tp"] for m in metrics.values())
    total_fp = sum(m["fp"] for m in metrics.values())
    total_fn = sum(m["fn"] for m in metrics.values())
    overall_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    overall_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    overall_f1 = (2 * overall_p * overall_r / (overall_p + overall_r)) if (overall_p + overall_r) > 0 else 0

    print("═" * 80)
    print(f"  OVERALL  |  Precision: {overall_p:.3f}  |  Recall: {overall_r:.3f}  |  F1: {overall_f1:.3f}")
    print("═" * 80)
    print()
    print("NOTE: These numbers are over PLANTED ground truth only. In production, the")
    print("'true' break rate is unknown; these metrics cannot be replicated without")
    print("a separate labelling process.")
    print()


if __name__ == "__main__":
    gt_path = DATA_DIR / "ground_truth.csv"
    if not gt_path.exists():
        print(f"ERROR: {gt_path} not found. Run generate_data.py first.", file=sys.stderr)
        sys.exit(1)

    print("Loading ground truth...")
    ground_truth = load_ground_truth(gt_path)
    print(f"  {len(ground_truth)} planted breaks loaded")

    print("Loading engine predictions from database...")
    try:
        predictions = load_engine_predictions(DB_URL)
    except Exception as e:
        print(f"ERROR connecting to database: {e}", file=sys.stderr)
        print("Make sure the reconciliation job has been run first.", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(predictions)} detected breaks loaded")

    metrics = compute_metrics(ground_truth, predictions)
    print_report(metrics)
