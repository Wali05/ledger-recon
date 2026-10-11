"""Authentication, reviewer identity and the append-only review history."""

import pytest

from app.auth import load_keys
from tests.test_api import pair, run

ALICE = "alice-key-0123456789"
BOB = "bob-key-0123456789ab"


def first_break(client, headers=None):
    return client.get("/breaks?source=uploaded", headers=headers).json()["items"][0]


def test_local_mode_records_reviewer_note_and_history(client):
    pair(client)
    run(client)
    record = first_break(client)
    url = f"/breaks/{record['break_id']}"
    resolved = client.post(url + "/resolve", json={"note": "Bank fee confirmed"}).json()
    assert resolved["resolved"] and resolved["resolved_by"] == "local"
    # Repeating the action does not add an event or move the timestamp.
    again = client.post(url + "/resolve", json={"note": "second click"}).json()
    assert again["resolved_at"] == resolved["resolved_at"]
    assert again["message"] == "Break was already resolved"
    reopened = client.post(url + "/reopen", json={"note": "Fee was refunded"}).json()
    assert not reopened["resolved"] and reopened["resolved_at"] is None
    events = client.get(url + "/events").json()
    assert [(e["action"], e["reviewer"], e["note"]) for e in events] == [
        ("resolved", "local", "Bank fee confirmed"),
        ("reopened", "local", "Fee was refunded"),
    ]
    assert client.get(url).json()["resolved_by"] is None
    # Resolve also works without a body, as older clients send it.
    assert client.post(url + "/resolve").json()["resolved"] is True


def test_history_survives_dataset_replacement(client):
    pair(client)
    run(client)
    record = first_break(client)
    client.post(f"/breaks/{record['break_id']}/resolve", json={"note": "ok"})
    replacement = "transaction_id,amount,timestamp,description\nT1,97,2024-06-01T12:00:00Z,x\n"
    assert pair(client, statement=replacement).json()["replaced"] is True
    assert client.get("/breaks?source=uploaded").json()["total"] == 0
    audit = client.get("/audit?source=uploaded").json()
    assert [(e["transaction_id"], e["action"]) for e in audit] == [("T1", "resolved")]


def test_api_keys_protect_every_data_endpoint_and_identify_reviewers(client, monkeypatch):
    monkeypatch.setenv("API_KEYS", f"alice:{ALICE},bob:{BOB}")
    assert client.get("/health").status_code == 200
    assert client.get("/session").json() == {"auth_required": True, "reviewer": None}
    for method, path in [
        ("get", "/stats"),
        ("get", "/breaks"),
        ("get", "/audit"),
        ("get", "/reconcile/jobs"),
        ("post", "/reconcile/run"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 401, path
        assert response.headers["www-authenticate"] == "Bearer"
    wrong = {"Authorization": "Bearer not-a-real-key-000000"}
    assert client.get("/stats", headers=wrong).status_code == 401
    alice = {"Authorization": f"Bearer {ALICE}"}
    bob = {"Authorization": f"Bearer {BOB}"}
    assert client.get("/session", headers=alice).json()["reviewer"] == "alice"
    assert pair_with(client, alice).status_code == 200
    run_with(client, alice)
    record = first_break(client, alice)
    url = f"/breaks/{record['break_id']}"
    assert client.post(url + "/resolve", headers=bob).json()["resolved_by"] == "bob"
    client.post(url + "/reopen", headers=alice, json={"note": "needs evidence"})
    events = client.get(url + "/events", headers=alice).json()
    assert [(e["action"], e["reviewer"]) for e in events] == [
        ("resolved", "bob"),
        ("reopened", "alice"),
    ]


def pair_with(client, headers):
    ledger = "transaction_id,account_id,amount,currency,timestamp\nT1,A,100,USD,2024-06-01\n"
    statement = "transaction_id,amount,timestamp\nT1,98,2024-06-01\n"
    return client.post(
        "/reconcile/upload",
        headers=headers,
        files={"ledger": ("l.csv", ledger), "statement": ("s.csv", statement)},
    )


def run_with(client, headers):
    job = client.post("/reconcile/run?source=uploaded", headers=headers).json()["job_id"]
    assert client.get(f"/reconcile/status/{job}", headers=headers).json()["status"] == "complete"


@pytest.mark.parametrize(
    "value", ["alice", "alice:short", ":nobody-0123456789", "a/b:0123456789abcdef"]
)
def test_malformed_api_keys_fail_fast(value):
    with pytest.raises(ValueError):
        load_keys(value)


def test_note_length_is_validated(client):
    pair(client)
    run(client)
    record = first_break(client)
    response = client.post(f"/breaks/{record['break_id']}/resolve", json={"note": "x" * 1001})
    assert response.status_code == 422
