# SPDX-License-Identifier: AGPL-3.0-only
"""Signed saved Ask integration over the real adapter and model SDK stubs."""

import json
from dataclasses import fields

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import recheck_grant
from app.config import settings
from app.controls.admission import jobs
from app.controls.data import data
from app.controls.worker import run_one
from app.conversations.ledger import DeletionLedger
from app.conversations.migration import migrate
from app.conversations.models import Message, Turn
from app.conversations.policy import Policy
from app.conversations.repository import ConversationStore
from app.conversations.router import build_router
from app.packs._skeleton.pack import SkeletonPack
from app.store import ConsentRouter, InMemoryStore
from tests.http_auth import token
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_jobs_http import job_boundary  # noqa: F401
from tests.test_jobs_worker import worker  # noqa: F401


@pytest.fixture
def saved_worker(worker, grant_boundary, monkeypatch, tmp_path):  # noqa: F811
    _, store, path, auth, adapter, responses, calls = worker
    migrate(store.ledger.engine)
    policy = Policy(
        enabled=True,
        policy_id="saved-test",
        retention_seconds=600,
        backup_max_age_seconds=600,
        deletion_ledger_file=str(tmp_path / "deleted.jsonl"),
    )
    for field in fields(policy):
        monkeypatch.setattr(settings, "dialogue_" + field.name, getattr(policy, field.name))
    monkeypatch.setattr(settings, "controls_mode", "enforced")
    DeletionLedger(policy.deletion_ledger_file).initialize()
    repo = ConversationStore(store.ledger.engine, policy, lambda: int(store.ledger.clock()))
    store.dialogue = repo
    from app.conversations import router as dialogue_router

    monkeypatch.setattr(dialogue_router, "ConversationStore", lambda *args: repo)
    identity = recheck_grant(grant_boundary[0])
    cid = repo.create(identity, "create")["conversation_id"]
    app = FastAPI()
    for prefix in ("/api", "/quad/v1"):
        app.include_router(
            build_router(
                prefix,
                ConsentRouter(InMemoryStore()),
                SkeletonPack(),
                lambda: pytest.fail("HTTP must not construct a model"),
                engine=repo.engine,
                policy=policy,
            )
        )
    client = TestClient(app, headers={"Authorization": "Bearer " + token("original")})
    return client, store, repo, identity, cid, adapter, responses, calls, path, auth


def body(**changes):
    return dict(
        request_id="saved_request_001",
        participant_id="gh:1",
        exercise_id="echo-1",
        exercise_version="v1",
        expected_revision=0,
        message="Explain loops",
        stance="peer",
        **changes,
    )


def submit(env, prefix="/api", payload=None):
    reply = env[0].post(f"{prefix}/conversations/{env[4]}/jobs", json=payload or body())
    assert reply.status_code == 202, reply.text
    return reply.json()["id"]


def status(env, prefix="/api"):
    now = max(env[1].ledger.clock(), 103.0)
    env[1].ledger.clock = lambda: now
    return env[0].get(f"{prefix}/conversations/{env[4]}/jobs/by-request/saved_request_001")


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
def test_saved_duplicate_one_execution_two_messages_and_exact_settlement(saved_worker, prefix):
    client, store, repo, identity, cid, adapter, _, calls, _, _ = saved_worker
    job_id = submit(saved_worker, prefix)
    assert submit(saved_worker, prefix) == job_id
    assert repo.get(identity, cid)["revision"] == 0  # Queue wait is not a turn lease.
    assert run_one(store.admission, adapter) and not run_one(store.admission, adapter)
    result = status(saved_worker, prefix)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value["state"] == "completed" and value["result"]["message"].strip()
    assert value["result"]["revision"] == 2
    assert "planner_note" not in value["result"] and "live_signals" not in value["result"]
    assert submit(saved_worker, prefix) == job_id and len(calls) == 3
    assert len(repo.history(identity, cid)["messages"]) == 2
    assert store.ledger.summary()["consumed"]["tokens"] == 45
    assert (
        client.post(
            f"{prefix}/conversations/{cid}/jobs", json={**body(), "message": "Changed"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("phase", ["queued", "after_call", "staged", "completed"])
def test_delete_erases_linked_input_results_and_never_resurrects(saved_worker, phase, monkeypatch):
    _, store, repo, identity, cid, adapter, _, calls, _, _ = saved_worker
    submit(saved_worker)
    if phase == "after_call":
        llm = adapter.llm.factory()
        create = llm._client.chat.completions.create

        def remove(**kwargs):
            answer = create(**kwargs)
            repo.delete(identity, cid)
            return answer

        llm._client.chat.completions.create = remove
    elif phase == "staged":
        publish = adapter.publish

        def remove_staged(job, ref):
            repo.delete(identity, cid)
            publish(job, ref)

        monkeypatch.setattr(adapter, "publish", remove_staged)
    if phase == "queued":
        repo.delete(identity, cid)
    run_one(store.admission, adapter)
    if phase == "completed":
        repo.delete(identity, cid)
    assert status(saved_worker).status_code == 404
    assert not run_one(store.admission, adapter)
    with store.ledger.transaction() as conn:
        assert conn.execute(select(data)).all() == []
    with repo.sessions() as session:
        assert session.scalars(select(Message)).all() == []
    assert len(calls) == (0 if phase == "queued" else 1 if phase == "after_call" else 3)


@pytest.mark.parametrize("change", ["revoked", "version", "expiry", "revision", "policy"])
def test_live_changes_between_inference_and_publication_block_result(
    saved_worker, change, monkeypatch
):
    _, store, repo, identity, cid, adapter, _, calls, path, auth = saved_worker
    submit(saved_worker)
    publish = adapter.publish

    def changed(job, ref):
        if change == "revoked":
            del auth["subjects"]["original"]
            path.write_text(json.dumps(auth))  # 'other' still has the same learner.
        elif change == "version":
            auth["exercise_versions"]["echo-1"] = "v2"
            path.write_text(json.dumps(auth))
        elif change == "expiry":
            store.ledger.clock = lambda: 701.0
        elif change == "policy":
            from dataclasses import replace

            repo.policy = replace(repo.policy, policy_id="next-policy")
        else:
            from app.conversations.models import Conversation

            with repo.sessions.begin() as session:
                session.get(Conversation, cid).revision += 1
        publish(job, ref)

    monkeypatch.setattr(adapter, "publish", changed)
    assert run_one(store.admission, adapter) and len(calls) == 3
    with store.ledger.transaction() as conn:
        row = conn.execute(select(jobs)).mappings().one()
        assert row["state"] != "completed" and row["result_ref"] is None
    with repo.sessions() as session:
        assert len(session.scalars(select(Message)).all()) == 1


def test_unknown_provider_result_holds_budget_and_recovery_never_reexecutes(saved_worker):
    _, store, repo, identity, cid, adapter, responses, calls, _, _ = saved_worker
    submit(saved_worker)
    responses[:] = [TimeoutError()]
    assert run_one(store.admission, adapter)
    assert status(saved_worker).json()["state"] == "unknown"
    assert submit(saved_worker) and not run_one(store.admission, adapter)
    assert store.ledger.summary()["reserved"]["tokens"] > 0 and len(calls) == 1
    assert len(repo.history(identity, cid)["messages"]) == 1


def test_atomic_publish_failure_rolls_back_assistant_and_result(saved_worker, monkeypatch):
    _, store, repo, _, _, adapter, _, calls, _, _ = saved_worker
    submit(saved_worker)

    class Crash(BaseException):
        pass

    def fail(*args, **kwargs):
        raise Crash("commit interrupted")

    monkeypatch.setattr(store.admission, "finish", fail)
    with pytest.raises(Crash):
        run_one(store.admission, adapter)
    with repo.sessions() as session:
        assert len(session.scalars(select(Message)).all()) == 1
        assert session.scalars(select(Turn)).one().status == "pending"
    with store.ledger.transaction() as conn:
        assert conn.execute(select(jobs.c.state)).scalar_one() == "running"
    store.ledger.clock = lambda: 161.0
    assert status(saved_worker).json()["state"] == "unknown"
    assert not run_one(store.admission, adapter) and len(calls) == 3


def test_split_database_saved_path_fails_closed(saved_worker, monkeypatch):
    from app.controls import saved
    from app.controls.contracts import ControlError

    _, store, *_ = saved_worker
    del store.dialogue
    with pytest.raises(ControlError, match="saved_database_mismatch"):
        saved.repository(store)


def test_queued_revision_conflict_executes_only_first_turn(saved_worker):
    client, store, repo, identity, cid, adapter, _, calls, _, _ = saved_worker
    submit(saved_worker)
    other = {**body(), "request_id": "saved_request_002"}
    assert client.post(f"/api/conversations/{cid}/jobs", json=other).status_code == 202
    assert run_one(store.admission, adapter)
    assert run_one(store.admission, adapter)
    assert len(calls) == 3 and len(repo.history(identity, cid)["messages"]) == 2
    with store.ledger.transaction() as conn:
        assert sorted(conn.execute(select(jobs.c.state)).scalars()) == ["completed", "failed"]


def test_lost_publication_ack_recovers_committed_reply_without_new_calls(saved_worker, monkeypatch):
    _, store, repo, identity, cid, adapter, _, calls, _, _ = saved_worker
    submit(saved_worker)
    publish = adapter.publish

    def lost(*args):
        publish(*args)
        raise RuntimeError("ack lost")

    monkeypatch.setattr(adapter, "publish", lost)
    assert run_one(store.admission, adapter)
    assert status(saved_worker).json()["state"] == "completed"
    assert len(repo.history(identity, cid)["messages"]) == 2
    assert not run_one(store.admission, adapter) and len(calls) == 3


def test_model_json_retry_is_separate_accounting_not_a_second_turn(saved_worker):
    from tests.test_controls_execution import response

    _, store, repo, identity, cid, adapter, responses, calls, _, _ = saved_worker
    responses.insert(0, response("invalid JSON"))
    submit(saved_worker)
    assert run_one(store.admission, adapter)
    assert status(saved_worker).json()["state"] == "completed"
    assert len(calls) == 4 and store.ledger.summary()["consumed"]["tokens"] == 60
    assert len(repo.history(identity, cid)["messages"]) == 2


def test_expiry_cleanup_erases_linked_content_and_dialogue(saved_worker):
    _, store, repo, identity, cid, adapter, _, _, _, _ = saved_worker
    submit(saved_worker)
    assert run_one(store.admission, adapter)
    store.ledger.clock = lambda: 701.0
    assert repo.cleanup() == 1
    assert status(saved_worker).status_code == 404
    with store.ledger.transaction() as conn:
        assert conn.execute(select(data)).all() == []
    with repo.sessions() as session:
        assert session.scalars(select(Message)).all() == []


def test_original_subject_only_can_query_old_job_even_with_same_learner(saved_worker):
    client, store, _, _, cid, adapter, _, calls, _, _ = saved_worker
    submit(saved_worker)
    assert run_one(store.admission, adapter)
    reply = client.get(
        f"/api/conversations/{cid}/jobs/by-request/saved_request_001",
        headers={"Authorization": "Bearer " + token("other")},
    )
    assert reply.status_code == 404 and len(calls) == 3


def test_saved_support_uses_placeholders_and_never_persists_distress(saved_worker, monkeypatch):
    from app.conversations.router import PLACEHOLDER

    _, store, repo, identity, cid, adapter, _, calls, _, _ = saved_worker
    monkeypatch.setattr(settings, "distress_routing_enabled", True)
    payload = {**body(), "message": "I want to kill myself"}
    submit(saved_worker, payload=payload)
    assert run_one(store.admission, adapter)
    result = status(saved_worker).json()
    assert result["state"] == "completed" and result["result"]["message"] != PLACEHOLDER
    assert calls == []
    assert all(m["text"] == PLACEHOLDER for m in repo.history(identity, cid)["messages"])
    with store.ledger.transaction() as conn:
        for row in conn.execute(select(data)).mappings():
            assert "kill myself" not in store.cipher.decrypt(row["body"].encode()).decode()
