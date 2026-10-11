import csv
import io
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

LEDGER_HEADER = "transaction_id,account_id,amount,currency,timestamp,description\n"
STATEMENT_HEADER = "transaction_id,amount,timestamp,description\n"
DATE = "2024-06-01T12:00:00Z"


def pair(client, ledger=None, statement=None):
    ledger = ledger or LEDGER_HEADER + f"T1,A,100.0000,USD,{DATE},payment\n"
    statement = statement or STATEMENT_HEADER + f"T1,98.0000,{DATE},payment\n"
    return client.post(
        "/reconcile/upload",
        files={
            "ledger": ("ledger.csv", ledger.encode("utf-8-sig"), "text/csv"),
            "statement": ("statement.csv", statement.encode("utf-8-sig"), "text/csv"),
        },
    )


def run(client, source="uploaded"):
    accepted = client.post(f"/reconcile/run?source={source}")
    assert accepted.status_code == 202, accepted.text
    status = client.get("/reconcile/status/" + accepted.json()["job_id"])
    assert status.status_code == 200, status.text
    return status.json()


def test_upload_reconcile_resolve_rerun_preserves_evidence(client):
    assert pair(client).status_code == 200
    first = run(client)
    assert first["status"] == "complete"
    assert (first["breaks_detected"], first["breaks_inserted"]) == (1, 1)
    record = client.get("/breaks?source=uploaded").json()["items"][0]
    assert record["source"] == "uploaded"
    assert record["internal_amount"] == "100.0000"
    assert record["external_transaction_id"] == "T1"
    assert record["internal_timestamp"].endswith("Z")
    url = f"/breaks/{record['break_id']}/resolve"
    resolved = client.post(url).json()
    assert client.post(url).json()["resolved_at"] == resolved["resolved_at"]
    second = run(client)
    assert (second["breaks_detected"], second["breaks_inserted"]) == (1, 0)
    assert pair(client).json()["replaced"] is False
    current = client.get(f"/breaks/{record['break_id']}").json()
    assert current["resolved"] and current["resolved_at"] == resolved["resolved_at"]
    assert client.get("/stats?source=uploaded").json()["resolution_rate_pct"] == 100


def test_upload_preserves_every_extra_duplicate_from_both_feeds(client):
    ledger = LEDGER_HEADER + f"T1,A,100,EUR,{DATE},same\n" * 3
    statement = STATEMENT_HEADER + f"T1,100,{DATE},same\n" * 4
    response = pair(client, ledger, statement)
    assert response.json()["ledger_rows"] == 3
    assert response.json()["statement_rows"] == 4
    assert run(client)["breaks_detected"] == 5
    items = client.get("/breaks?source=uploaded").json()["items"]
    assert {row["break_type"] for row in items} == {"DUPLICATE"}
    assert len({(row["evidence_side"], row["occurrence"]) for row in items}) == 5
    assert run(client)["breaks_inserted"] == 0


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "0.00001", "100000000000000", "nope", ""])
def test_invalid_upload_is_atomic_and_does_not_claim_success(client, amount):
    pair(client)
    run(client)
    before = client.get("/breaks?source=uploaded").json()
    bad = STATEMENT_HEADER + f"T1,99,{DATE},valid\nT2,{amount},{DATE},bad\n"
    result = pair(client, statement=bad)
    assert result.status_code == 400
    assert "line 3" in result.json()["detail"]
    assert client.get("/breaks?source=uploaded").json() == before
    assert run(client)["breaks_detected"] == 1


@pytest.mark.parametrize(
    "content",
    [
        "transaction_id,amount,timestamp\n",
        "transaction_id,amount,amount,timestamp\nT1,1,2,2024-01-01\n",
        "transaction_id,amount,timestamp\n,1,2024-01-01\n",
        "wrong,headers\n1,2\n",
        "transaction_id,amount,timestamp\nT1,1,not-a-date\n",
        "transaction_id,amount,timestamp\nT1,1,2024-01-01,extra\n",
        "transaction_id,amount,timestamp,description\nT1,1,2024-01-01,bad\0text\n",
    ],
)
def test_malformed_or_empty_csv_is_rejected(client, content):
    assert (
        client.post("/reconcile/upload/statement", files={"file": ("bad.csv", content)}).status_code
        == 400
    )


def test_decimal_amount_survives_upload_matching_storage_and_export(client):
    ledger = LEDGER_HEADER + f"T1,A,90071992547409.1234,USD,{DATE},large exact amount\n"
    statement = STATEMENT_HEADER + f"T1,90071992547409.1233,{DATE},large exact amount\n"
    assert pair(client, ledger, statement).status_code == 200
    assert run(client)["status"] == "complete"
    record = client.get("/breaks?source=uploaded").json()["items"][0]
    assert Decimal(record["delta_amount"]) == Decimal("0.0001")
    assert record["internal_amount"] == "90071992547409.1234"
    exported = client.get("/breaks/export?source=uploaded").text
    assert "90071992547409.1234" in exported and "0.0001" in exported


def test_large_signed_difference_is_representable(client):
    ledger = LEDGER_HEADER + f"T1,A,99999999999999.9999,USD,{DATE},positive\n"
    statement = STATEMENT_HEADER + f"T1,-99999999999999.9999,{DATE},negative\n"
    pair(client, ledger, statement)
    assert run(client)["status"] == "complete"
    assert (
        client.get("/breaks?source=uploaded").json()["items"][0]["delta_amount"]
        == "199999999999999.9998"
    )


def test_new_dataset_invalidates_old_results_and_requires_fresh_run(client):
    pair(client)
    run(client)
    assert pair(client, statement=STATEMENT_HEADER + f"T1,100,{DATE},now agrees\n").json()[
        "replaced"
    ]
    assert client.get("/breaks?source=uploaded").json()["total"] == 0
    assert client.get("/reconcile/jobs?source=uploaded").json() == []
    assert run(client)["breaks_detected"] == 0


def test_stats_count_the_feeds_used_by_the_matcher_and_isolate_sources(client):
    initial = client.get("/stats").json()
    assert initial["total_transactions_in_ledger"] > 5000
    assert initial["total_transactions_in_statement"] > 5000
    assert not initial["ai_enabled"]
    pair(client)
    run(client)
    stats = client.get("/stats?source=uploaded").json()
    assert stats["total_transactions_in_ledger"] == stats["total_transactions_in_statement"] == 1
    assert stats["total_breaks_detected"] == 1
    assert client.get("/breaks?source=synthetic").json()["total"] == 0


@pytest.mark.parametrize(
    "path",
    [
        "/stats?source=typo",
        "/breaks?source=typo",
        "/breaks?break_type=typo",
        "/breaks?sort_by=bogus",
        "/reconcile/status/not-a-uuid",
        "/breaks?page=0",
    ],
)
def test_invalid_queries_return_validation_errors(client, path):
    assert client.get(path).status_code == 422


def test_invalid_source_and_missing_uploads_cannot_create_jobs(client):
    assert client.post("/reconcile/run?source=typo").status_code == 422
    assert client.post("/reconcile/run?source=uploaded").status_code == 409
    assert client.get("/reconcile/jobs?source=uploaded").json() == []


def test_sorting_is_numeric_and_global_before_pagination(client):
    amounts = [100, 2, 30, 4, 50, 6]
    ledger = LEDGER_HEADER + "".join(
        f"T{i},A,{amount},USD,{DATE},sort\n" for i, amount in enumerate(amounts)
    )
    statement = STATEMENT_HEADER + "".join(
        f"T{i},{amount - 1},{DATE},sort\n" for i, amount in enumerate(amounts)
    )
    pair(client, ledger, statement)
    run(client)
    response = client.get(
        "/breaks?source=uploaded&sort_by=internal_amount&sort_dir=asc&page_size=2&page=2"
    ).json()
    assert [Decimal(row["internal_amount"]) for row in response["items"]] == [
        Decimal(6),
        Decimal(30),
    ]
    assert response["total"] == 6


def test_csv_export_has_headers_when_empty_and_escapes_formula_text(client):
    empty = client.get("/breaks/export")
    assert "transaction_id" in empty.text
    ledger = LEDGER_HEADER + f"=SUM(1),A,100,USD,{DATE},@formula\n"
    statement = STATEMENT_HEADER + f"=SUM(1),99,{DATE},same\n"
    pair(client, ledger, statement)
    run(client)
    rows = list(csv.DictReader(io.StringIO(client.get("/breaks/export?source=uploaded").text)))
    assert rows[0]["transaction_id"] == "'=SUM(1)"
    assert client.get("/breaks/export?source=uploaded&resolved=true").text.count("\n") == 1


def test_parallel_job_admission_and_uploads_respect_the_dataset_lock(client, monkeypatch):
    from app.api import reconcile

    pair(client)
    monkeypatch.setattr(reconcile, "_run_local", lambda *args: None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: client.post("/reconcile/run?source=uploaded").status_code, range(2))
        )
    assert sorted(results) == [202, 409]
    assert pair(client).status_code == 409
    assert client.get("/reconcile/jobs?source=uploaded").json()[0]["status"] == "pending"


def test_failed_dispatch_records_failure_and_releases_admission(client, monkeypatch):
    from app.api import reconcile

    pair(client)
    monkeypatch.setattr(reconcile, "EAGER_MODE", False)

    def unavailable(*args, **kwargs):
        raise ConnectionError("unavailable")

    monkeypatch.setattr(reconcile.reconciliation_task, "apply_async", unavailable)
    assert client.post("/reconcile/run?source=uploaded").status_code == 503
    assert client.get("/reconcile/jobs?source=uploaded").json()[0]["status"] == "failed"
    assert pair(client).status_code == 200


def test_worker_failure_does_not_publish_partial_results(client, monkeypatch):
    from app import tasks

    pair(client)

    def broken(*args):
        raise RuntimeError("deliberate regression test")

    monkeypatch.setattr(tasks, "run_matching", broken)
    assert run(client)["status"] == "failed"
    assert client.get("/breaks?source=uploaded").json()["total"] == 0


def test_redelivered_completed_task_is_a_noop(client):
    from app.tasks import reconciliation_task

    pair(client)
    job = run(client)
    before = client.get("/breaks?source=uploaded").json()
    assert (
        reconciliation_task.apply(args=[job["job_id"], "uploaded"], throw=True).result["status"]
        == "complete"
    )
    assert client.get("/breaks?source=uploaded").json() == before


def test_ai_disabled_and_cached_explanations_are_honest(client, monkeypatch):
    from app.api import explanations

    pair(client)
    run(client)
    record = client.get("/breaks?source=uploaded").json()["items"][0]
    path = f"/breaks/{record['break_id']}/ai-explain"
    assert client.post(path).status_code == 503
    calls = []

    async def fake(record, key):
        calls.append(record.break_id)
        return "A fee may explain the difference. Verify the original statement."

    monkeypatch.setenv("GEMINI_API_KEY", "test-only-no-provider-call")
    monkeypatch.setattr(explanations, "generate_explanation", fake)
    assert client.get("/stats").json()["ai_enabled"]
    first = client.post(path).json()
    assert client.post(path).json() == first and len(calls) == 1
    assert (
        client.get(f"/breaks/{record['break_id']}").json()["ai_explanation"] == first["explanation"]
    )
