# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import recheck_grant
from app.controls.contracts import ControlError
from app.controls.data import ExecutionData, bindings, data
from app.controls.ledger import metadata
from tests.test_execution_grants import grant_boundary  # noqa: F401

ANSWER = dict(
    affective_state="neutral",
    affect_reasoning="",
    confidence=0.5,
    intervention="hint",
    planner_note="",
    self_critique="",
    governance="pass",
    memory={},
    message="A useful answer",
)


@pytest.fixture
def execution_data(ledger, grant_boundary):  # noqa: F811
    grant, path, auth = grant_boundary
    metadata.create_all(ledger.engine)
    store = ExecutionData(ledger, "test", Fernet.generate_key())
    return store, recheck_grant(grant), path, auth


def test_duplicate_has_one_owned_encrypted_input_and_atomic_result(execution_data):
    store, identity, _, _ = execution_data
    job = store.submit(identity, "stable", {"source": "private pedagogical input"}, "api")
    assert store.submit(identity, "stable", {"source": "private pedagogical input"}, "api") == job
    with store.ledger.transaction() as conn:
        rows = list(conn.execute(select(data)).mappings())
        assert len(rows) == 1 and "private pedagogical input" not in rows[0]["body"]
        assert "Bearer" not in conn.execute(select(bindings.c.grant)).scalar_one()
    claimed = store.admission.claim()
    assert store.load(claimed)[1]["source"] == "private pedagogical input"
    ref = store.stage(claimed, ANSWER)
    assert store.status(identity, job["id"])["state"] == "running"
    store.publish(claimed, ref)
    store.ledger.clock = lambda: 103.0
    assert store.status(identity, job["id"])["result"]["message"] == ANSWER["message"]
    with store.ledger.transaction() as conn:
        assert [r.kind for r in conn.execute(select(data))] == ["result"]
    with pytest.raises(ControlError, match="stale_worker"):
        store.publish(claimed, ref)


def test_conflict_and_rejected_admission_leave_no_orphan(execution_data):
    store, identity, _, _ = execution_data
    store.submit(identity, "same", {"source": "first"}, "api")
    with pytest.raises(ControlError, match="operation_conflict"):
        store.submit(identity, "same", {"source": "changed"}, "api")
    with pytest.raises((ControlError, ValueError)):
        store.submit(identity, "invalid id", {"source": "other"}, "api")
    with store.ledger.transaction() as conn:
        assert len(list(conn.execute(select(data)))) == 1
        assert len(list(conn.execute(select(bindings)))) == 1


def test_expiry_and_cleanup_do_not_erase_dedup_tombstones(execution_data):
    store, identity, _, _ = execution_data
    job = store.submit(identity, "stable", {}, "api")
    claimed = store.admission.claim()
    ref = store.stage(claimed, ANSWER)
    store.publish(claimed, ref)
    store.ledger.clock = lambda: 401.0
    assert store.status(identity, job["id"])["state"] == "result_expired"
    assert store.submit(identity, "stable", {}, "api")["state"] == "completed"
    assert store.admission.claim() is None
    with store.ledger.transaction() as conn:
        assert list(conn.execute(select(data))) == []


def test_revoked_original_cannot_load_publish_or_read(execution_data):
    store, identity, path, auth = execution_data
    job = store.submit(identity, "stable", {}, "api")
    claimed = store.admission.claim()
    ref = store.stage(claimed, ANSWER)
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    for action in [
        lambda: store.load(claimed),
        lambda: store.publish(claimed, ref),
        lambda: store.status(identity, job["id"]),
    ]:
        with pytest.raises(HTTPException):
            action()
    with store.ledger.transaction() as conn:
        assert conn.execute(select(data.c.kind).where(data.c.id == ref)).scalar_one() == "pending"


def test_crash_pending_result_does_not_reexecute(execution_data):
    store, identity, _, _ = execution_data
    job = store.submit(identity, "stable", {}, "api")
    claimed = store.admission.claim()
    store.stage(claimed, ANSWER)
    store.ledger.clock = lambda: 161.0
    assert store.status(identity, job["id"])["state"] == "unknown"
    assert store.admission.claim() is None
    assert store.cleanup() == 0  # status already removed terminal input/pending text


def test_publication_failure_rolls_back_result_and_completion(execution_data, monkeypatch):
    store, identity, _, _ = execution_data
    job = store.submit(identity, "stable", {}, "api")
    claimed = store.admission.claim()
    ref = store.stage(claimed, ANSWER)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated database failure before commit")

    monkeypatch.setattr(store.admission, "finish", fail)
    with pytest.raises(RuntimeError):
        store.publish(claimed, ref)
    assert store.status(identity, job["id"])["state"] == "running"
    with store.ledger.transaction() as conn:
        assert conn.execute(select(data.c.kind).where(data.c.id == ref)).scalar_one() == "pending"


def test_operational_storage_rejects_pii_and_never_keeps_distress_verbatim(
    execution_data, monkeypatch
):
    from app.config import settings

    store, identity, _, _ = execution_data
    with pytest.raises(ControlError, match="content_not_storable"):
        store.submit(identity, "pii", {"source": "person@example.invalid"}, "api")
    monkeypatch.setattr(settings, "distress_routing_enabled", True)
    raw = "I want to kill myself"
    job = store.submit(
        identity,
        "support",
        {
            "participant_id": "gh:1",
            "exercise_id": "echo-1",
            "recent": [{"who": "student", "text": raw}],
        },
        "api",
    )
    claimed = store.admission.claim()
    assert claimed["id"] == job["id"]
    body = store.load(claimed)[1]
    assert body["_support"] is True and raw not in json.dumps(body)
