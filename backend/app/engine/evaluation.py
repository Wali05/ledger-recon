"""Score transaction/type pairs, including UNKNOWN and multiple labels per ID.

This measures labels on synthetic fixtures, not duplicate-row recall or production
accuracy. Repeated occurrences of the same label on one ID count once.
"""

from app.engine.matcher import BREAK_TYPES


def compute_metrics(ground_truth, predictions):
    truth = set(ground_truth.items()) if isinstance(ground_truth, dict) else set(ground_truth)
    predicted = set(predictions.items()) if isinstance(predictions, dict) else set(predictions)
    metrics = {}
    kinds = list(BREAK_TYPES) + sorted({kind for _, kind in truth | predicted} - set(BREAK_TYPES))
    for kind in kinds:
        expected = {pair for pair in truth if pair[1] == kind}
        found = {pair for pair in predicted if pair[1] == kind}
        tp, fp, fn = len(expected & found), len(found - expected), len(expected - found)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        metrics[kind] = {
            "gt": len(expected),
            "pred": len(found),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        }
    tp, fp, fn = (sum(value[key] for value in metrics.values()) for key in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        "by_type": metrics,
        "overall": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        },
    }
