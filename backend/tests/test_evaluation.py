from app.engine.evaluation import compute_metrics


def test_unknown_predictions_count_as_false_positives_in_the_overall_score():
    result = compute_metrics(
        {("T1", "AMOUNT_MISMATCH")}, {("T1", "AMOUNT_MISMATCH"), ("T2", "UNKNOWN")}
    )
    assert result["overall"]["precision"] == 0.5
    assert result["by_type"]["UNKNOWN"]["fp"] == 1


def test_multiple_labels_for_one_transaction_are_not_overwritten():
    labels = {("T1", "DUPLICATE"), ("T1", "AMOUNT_MISMATCH")}
    assert compute_metrics(labels, labels)["overall"]["tp"] == 2
