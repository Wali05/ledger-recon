"""Split settlements end to end, triage filters, bulk review and evidence refresh."""

from decimal import Decimal

from app import tasks
from tests.test_api import DATE, LEDGER_HEADER, STATEMENT_HEADER, pair, run

LEDGER = LEDGER_HEADER + "".join(
    [
        f"INV-1,A,120.10,USD,{DATE},card\n",
        f"INV-2,A,75.25,USD,{DATE},card\n",
        f"INV-3,A,301.65,USD,{DATE},card\n",
        f"FEE-1,A,100.00,USD,{DATE},fee\n",
        f"REF-1,A,250.00,USD,{DATE},transfer\n",
        f"LONE-1,A,42.00,EUR,{DATE},pending\n",
    ]
)
STATEMENT = STATEMENT_HEADER + "".join(
    [
        f"DEP-9,497.00,{DATE},batch deposit\n",
        f"FEE-1,98.00,{DATE},fee\n",
        f"BNK-77,250.00,{DATE},incoming\n",
    ]
)


def breaks(client, query=""):
    return client.get("/breaks?source=uploaded&page_size=200" + query).json()


def by_type(client):
    return {item["break_type"]: item for item in breaks(client)["items"]}


def test_split_settlement_and_reference_mismatch_survive_storage(client):
    pair(client, LEDGER, STATEMENT)
    assert run(client)["breaks_detected"] == 4
    found = by_type(client)
    split = found["SPLIT_SETTLEMENT"]
    assert split["transaction_id"] == "DEP-9"
    assert split["related_ids"] == ["INV-1", "INV-2", "INV-3"]
    assert split["confidence"] == "medium"
    assert split["evidence_side"] == "many_internal"
    assert found["REFERENCE_MISMATCH"]["external_transaction_id"] == "BNK-77"
    assert found["MISSING_EXTERNAL"]["confidence"] == "high"
    exported = client.get("/breaks/export?source=uploaded&break_type=SPLIT_SETTLEMENT").text
    assert "confidence,related_ids" in exported.splitlines()[0]
    assert "INV-1 INV-2 INV-3" in exported


def test_search_matches_ids_partners_and_group_members_literally(client):
    pair(client, LEDGER, STATEMENT)
    run(client)
    assert {item["transaction_id"] for item in breaks(client, "&q=inv-2")["items"]} == {"DEP-9"}
    assert {item["transaction_id"] for item in breaks(client, "&q=bnk")["items"]} == {"REF-1"}
    # LIKE wildcards are literal: "_" must not match any single character.
    assert breaks(client, "&q=INV_1")["total"] == 0
    assert breaks(client, "&q=%25")["total"] == 0
    assert client.get("/breaks?q=" + "x" * 101).status_code == 422


def test_confidence_filter_and_triage_sort(client):
    pair(client, LEDGER, STATEMENT)
    run(client)
    medium = breaks(client, "&confidence=medium")["items"]
    assert [item["break_type"] for item in medium] == ["SPLIT_SETTLEMENT"]
    ordered = breaks(client, "&sort_by=confidence&sort_dir=asc")["items"]
    assert ordered[0]["confidence"] == "medium"
    assert {item["confidence"] for item in ordered[1:]} == {"high"}
    assert client.get("/breaks?confidence=certain").status_code == 422


def test_stats_report_open_exposure_by_type_and_confidence(client):
    pair(client, LEDGER, STATEMENT)
    run(client)
    stats = client.get("/stats?source=uploaded").json()
    values = {row["break_type"]: Decimal(row["open_value"]) for row in stats["breaks_by_type"]}
    # Amount breaks expose the difference; the rest expose the unconfirmed amount.
    assert values == {
        "AMOUNT_MISMATCH": Decimal("2"),
        "MISSING_EXTERNAL": Decimal("42"),
        "REFERENCE_MISMATCH": Decimal("250"),
        "SPLIT_SETTLEMENT": Decimal("497"),
    }
    assert Decimal(stats["open_value"]) == Decimal("791")
    assert stats["open_by_confidence"] == [
        {"confidence": "medium", "open_count": 1},
        {"confidence": "high", "open_count": 3},
    ]
    client.post(f"/breaks/{by_type(client)['SPLIT_SETTLEMENT']['break_id']}/resolve")
    assert Decimal(client.get("/stats?source=uploaded").json()["open_value"]) == Decimal("294")


def test_bulk_review_is_conditional_and_logs_each_change(client):
    pair(client, LEDGER, STATEMENT)
    run(client)
    ids = [item["break_id"] for item in breaks(client)["items"]]
    client.post(f"/breaks/{ids[0]}/resolve")
    body = {"action": "resolve", "break_ids": ids + [ids[1]], "note": "Batch confirmed"}
    result = client.post("/breaks/bulk-review", json=body).json()
    assert (result["changed"], result["unchanged"]) == (3, 1)
    assert result["message"] == "3 breaks resolved"
    assert client.get("/stats?source=uploaded").json()["resolution_rate_pct"] == 100
    history = client.get("/audit?source=uploaded").json()
    assert sum(event["note"] == "Batch confirmed" for event in history) == 3
    reopened = client.post(
        "/breaks/bulk-review", json={"action": "reopen", "break_ids": ids[:2]}
    ).json()
    assert reopened["changed"] == 2
    assert (
        client.post("/breaks/bulk-review", json={"action": "resolve", "break_ids": []}).status_code
        == 422
    )
    too_many = {"action": "resolve", "break_ids": [ids[0]] * 501}
    assert client.post("/breaks/bulk-review", json=too_many).status_code == 422


def test_rerun_refreshes_evidence_and_retires_breaks_the_rules_no_longer_report(
    client, monkeypatch
):
    pair(client, LEDGER, STATEMENT)
    run(client)
    before = by_type(client)
    kept = before["SPLIT_SETTLEMENT"]
    client.post(f"/breaks/{kept['break_id']}/resolve", json={"note": "Remittance matched"})
    real = tasks.run_matching

    def revised_rules(internal, external):
        records = [r for r in real(internal, external) if r.break_type != "MISSING_EXTERNAL"]
        for record in records:
            record.description = "Revised rule text"
        return records

    monkeypatch.setattr(tasks, "run_matching", revised_rules)
    result = run(client)
    assert (result["breaks_detected"], result["breaks_inserted"]) == (3, 0)
    assert result["breaks_retired"] == 1
    after = by_type(client)
    assert "MISSING_EXTERNAL" not in after
    current = after["SPLIT_SETTLEMENT"]
    assert current["break_id"] == kept["break_id"]
    assert current["resolved"] and current["detected_at"] == kept["detected_at"]
    assert current["description"] == "Revised rule text"
    # The retired break's review history is untouched; events never cascade.
    assert [e["note"] for e in client.get("/audit?source=uploaded").json()] == [
        "Remittance matched"
    ]
