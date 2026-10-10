# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest
from sqlalchemy import select

from app.controls.admission import jobs
from app.controls.contracts import Limits
from app.controls.jobs_worker import AskAdapter
from app.controls.worker import run_one
from app.packs._skeleton.pack import SkeletonPack
from app.store import ConsentRouter, InMemoryStore
from conftest import _CallStub, controls_policy
from tests.test_controls_execution import provider, response
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_jobs_http import BODY, job_boundary  # noqa: F401


@pytest.fixture
def worker(job_boundary, monkeypatch):  # noqa: F811
    client, store, path, auth = job_boundary
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    store.ledger.update_policy(controls_policy(version="funded", deployment=Limits(tokens=1000000)))
    stub = _CallStub()
    responses = [
        response(json.dumps(stub.json(role=role, tier="fast", system="", user="")))
        for role in ("planner", "reasoner", "self_eval")
    ]
    llm, calls = provider(responses)
    adapter = AskAdapter(store, ConsentRouter(InMemoryStore()), SkeletonPack(), lambda: llm)
    return client, store, path, auth, adapter, responses, calls


def submit(client, **kwargs):
    response = client.post("/api/sol/jobs", json={**BODY, "stance": "peer", **kwargs})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def status(client, store, job_id):
    store.ledger.clock = lambda: 103.0
    return client.get("/api/sol/jobs/" + job_id).json()


def test_real_loop_duplicate_http_executes_one_turn_and_recovers_result(worker):
    client, store, _, _, adapter, _, calls = worker
    job_id = submit(client)
    assert submit(client) == job_id
    assert run_one(store.admission, adapter)
    assert not run_one(store.admission, adapter)
    result = status(client, store, job_id)
    assert result["state"] == "completed" and result["result"]["message"].strip()
    assert len(calls) == 3
    assert store.ledger.summary()["consumed"]["tokens"] == 45
    # A lost completed HTTP response followed by the same POST never reruns.
    assert submit(client) == job_id
    assert not run_one(store.admission, adapter)


def test_revoked_original_before_dispatch_stops_despite_shared_learner(worker):
    client, store, path, auth, adapter, _, calls = worker
    job_id = submit(client)
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    assert run_one(store.admission, adapter)
    assert calls == []
    with store.ledger.transaction() as conn:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one()
        assert row["state"] == "failed" and row["reason"] == "authorization_revoked"


def test_revocation_after_first_external_attempt_prevents_next_and_publication(worker):
    client, store, path, auth, adapter, _, calls = worker
    job_id = submit(client)
    llm = adapter.llm.factory()
    create = llm._client.chat.completions.create

    def revoke(**kwargs):
        value = create(**kwargs)
        del auth["subjects"]["original"]
        path.write_text(json.dumps(auth))
        return value

    llm._client.chat.completions.create = revoke
    assert run_one(store.admission, adapter)
    assert len(calls) == 1
    with store.ledger.transaction() as conn:
        assert (
            conn.execute(select(jobs.c.result_ref).where(jobs.c.id == job_id)).scalar_one() is None
        )
    assert store.ledger.summary()["consumed"]["tokens"] == 15


def test_timeout_stays_unknown_and_never_releases_or_retries(worker):
    client, store, _, _, adapter, responses, calls = worker
    job_id = submit(client)
    responses[:] = [TimeoutError("private provider diagnostic")]
    assert run_one(store.admission, adapter)
    assert status(client, store, job_id)["state"] == "unknown"
    assert store.ledger.summary()["reserved"]["tokens"] > 0
    assert len(calls) == 1 and not run_one(store.admission, adapter)


def test_missing_usage_can_deliver_answer_without_refunding_hold(worker):
    client, store, _, _, adapter, responses, calls = worker
    for value in responses:
        value.usage = None
    job_id = submit(client)
    assert run_one(store.admission, adapter)
    assert status(client, store, job_id)["state"] == "completed"
    assert len(calls) == 3 and store.ledger.summary()["reserved"]["tokens"] > 0


def test_crash_after_staging_never_reexecutes_and_does_not_publish(worker, monkeypatch):
    client, store, _, _, adapter, _, calls = worker
    job_id = submit(client)

    class Crash(BaseException):
        pass

    def crash(*args):
        raise Crash()

    monkeypatch.setattr(adapter, "publish", crash)
    with pytest.raises(Crash):
        run_one(store.admission, adapter)
    store.ledger.clock = lambda: 161.0
    assert client.get("/api/sol/jobs/" + job_id).json()["state"] == "unknown"
    assert len(calls) == 3 and not run_one(store.admission, adapter)


def test_publication_commit_survives_lost_worker_response(worker, monkeypatch):
    client, store, _, _, adapter, _, calls = worker
    job_id = submit(client)
    publish = adapter.publish

    def lost(*args):
        publish(*args)
        raise RuntimeError("worker lost its acknowledgement")

    monkeypatch.setattr(adapter, "publish", lost)
    assert run_one(store.admission, adapter)
    assert status(client, store, job_id)["state"] == "completed"
    assert len(calls) == 3 and not run_one(store.admission, adapter)


def test_revoked_before_publication_cannot_publish_even_when_all_calls_settled(worker, monkeypatch):
    client, store, path, auth, adapter, _, calls = worker
    job_id = submit(client)
    publish = adapter.publish

    def revoked(*args):
        del auth["subjects"]["original"]
        path.write_text(json.dumps(auth))
        publish(*args)

    monkeypatch.setattr(adapter, "publish", revoked)
    assert run_one(store.admission, adapter)
    assert len(calls) == 3
    with store.ledger.transaction() as conn:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one()
        assert row["state"] == "failed" and row["result_ref"] is None
    assert store.ledger.summary()["consumed"]["tokens"] == 45


def test_control_and_distress_use_existing_deterministic_paths_without_model(worker, monkeypatch):
    from app.config import settings

    client, store, _, _, adapter, _, calls = worker
    job_id = submit(client, stance="control")
    assert run_one(store.admission, adapter)
    assert status(client, store, job_id)["state"] == "completed"
    monkeypatch.setattr(settings, "distress_routing_enabled", True)
    job_id = submit(
        client,
        request_id="support_request_002",
        recent=[{"who": "student", "text": "I want to kill myself"}],
    )
    assert run_one(store.admission, adapter)
    store.ledger.clock = lambda: 106.0
    result = client.get("/api/sol/jobs/" + job_id).json()
    assert result["state"] == "completed"
    assert result["result"]["affective_state"] == "distress" and calls == []


def test_queue_expiry_is_known_failure_not_execution(worker):
    client, store, _, _, adapter, _, calls = worker
    job_id = submit(client)
    store.ledger.clock = lambda: 221.0
    assert not run_one(store.admission, adapter)
    result = client.get("/api/sol/jobs/" + job_id).json()
    assert result["state"] == "failed" and result["reason"] == "queue_expired"
    assert calls == []


@pytest.mark.parametrize("during_call", [False, True])
def test_process_loss_before_or_during_send_preserves_unknown_without_replay(
    worker, monkeypatch, during_call
):
    client, store, _, _, adapter, _, _ = worker
    job_id = submit(client)

    class Crash(BaseException):
        pass

    def crash(*args, **kwargs):
        raise Crash()

    if during_call:
        monkeypatch.setattr(adapter.llm.factory()._client.chat.completions, "create", crash)
    else:
        monkeypatch.setattr(adapter, "execute", crash)
    with pytest.raises(Crash):
        run_one(store.admission, adapter)
    store.ledger.clock = lambda: 161.0
    assert client.get("/api/sol/jobs/" + job_id).json()["state"] == "unknown"
    assert not run_one(store.admission, adapter)
    held = store.ledger.summary()["reserved"]["tokens"]
    assert (held > 0) == during_call


def test_configured_support_resources_render_without_persisting_contacts(worker, monkeypatch):
    from app.config import settings
    from app.controls.data import data

    client, store, _, _, adapter, _, calls = worker
    monkeypatch.setattr(settings, "distress_routing_enabled", True)
    monkeypatch.setattr(settings, "distress_support_message", "Contact support@example.invalid")
    monkeypatch.setattr(settings, "distress_escalation_target", "your course support team")
    job_id = submit(client, recent=[{"who": "student", "text": "I want to kill myself"}])
    assert run_one(store.admission, adapter)
    result = status(client, store, job_id)
    assert result["state"] == "completed" and calls == []
    assert "support@example.invalid" in result["result"]["message"]
    with store.ledger.transaction() as conn:
        for row in conn.execute(select(data)).mappings():
            content = store.cipher.decrypt(row["body"].encode()).decode()
            assert "support@example.invalid" not in content and "kill myself" not in content
