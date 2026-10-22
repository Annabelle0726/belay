# SPDX-License-Identifier: AGPL-3.0-only
"""Trusted behavior permissions across real HTTP/worker/recovery adapters."""

import json
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app.agent.injection_guard import InjectionGuard, SovereignLLMClient
from app.config import settings
from app.controls.admission import jobs
from app.controls.contracts import ControlError
from app.controls.data import bindings
from app.controls.ledger import attempts
from app.controls.runtime import operation
from app.controls.worker import run_one
from conftest import CONTROL_SCOPE as SCOPE
from tests.test_controls_execution import funded, response
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_jobs_http import BODY
from tests.test_jobs_http import job_boundary as job_boundary_fixture
from tests.test_jobs_worker import submit
from tests.test_jobs_worker import worker as worker_fixture


def change(path, auth, *, generation=None, revision=None, pairs=None):
    policy = auth["subjects"]["original"][0]["assignments"]["echo-1"]
    if generation is not None:
        policy["generation"] = generation
    if revision is not None:
        policy["policy_revision"] = revision
    if pairs is not None:
        policy["allowed_pairs"] = pairs
    path.write_text(json.dumps(auth))


@pytest.mark.parametrize("prefix", ["/api/sol/jobs", "/quad/v1/jobs"])
@pytest.mark.parametrize("legacy", [False, True])
def test_unapproved_pair_rejected_before_queue(job_boundary, prefix, legacy):
    client, store, path, auth = job_boundary
    if legacy:
        auth["subjects"]["original"][0]["assignments"]["echo-1"] = "v1"
        path.write_text(json.dumps(auth))
    else:
        change(path, auth, pairs=[{"mode": "study", "stance": "peer"}])
    assert client.post(prefix, json=BODY).status_code == 404
    with store.ledger.transaction() as conn:
        assert not list(conn.execute(select(jobs)))
        assert not list(conn.execute(select(attempts)))


@pytest.mark.parametrize("when", ["queued", "running", "completed"])
@pytest.mark.parametrize("change_kind", ["revision", "generation", "pairs"])
def test_policy_change_blocks_old_work_and_delivery(worker, when, change_kind):
    client, store, path, auth, adapter, _, calls = worker
    job_id = submit(client)

    def update():
        changes = {
            "revision": {"revision": 2},
            "generation": {"generation": "regranted-2"},
            "pairs": {"pairs": [{"mode": "study", "stance": "peer"}]},
        }
        change(path, auth, **changes[change_kind])

    if when == "queued":
        update()
    elif when == "running":
        llm = adapter.llm.factory()
        original = llm._client.chat.completions.create

        def send(**kwargs):
            result = original(**kwargs)
            update()
            return result

        llm._client.chat.completions.create = send
    assert run_one(store.admission, adapter)
    if when == "completed":
        update()
    assert len(calls) == {"queued": 0, "running": 1, "completed": 3}[when]
    assert client.get("/api/sol/jobs/" + job_id).status_code == 404
    with store.ledger.transaction() as conn:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().one()
        if when != "completed":
            assert row["state"] != "completed"
    assert (
        store.ledger.summary()["consumed"]["tokens"]
        == {"queued": 0, "running": 15, "completed": 45}[when]
    )


def test_preupgrade_job_binding_is_unavailable(job_boundary):
    client, store, _, _ = job_boundary
    job_id = client.post("/api/sol/jobs", json=BODY).json()["id"]
    with store.ledger.transaction() as conn:
        raw = json.loads(
            conn.execute(select(bindings.c.grant).where(bindings.c.id == job_id)).scalar_one()
        )
        raw.pop("authorization")
        conn.execute(bindings.update().where(bindings.c.id == job_id).values(grant=json.dumps(raw)))
    assert client.get("/api/sol/jobs/" + job_id).status_code == 404


@pytest.mark.parametrize("outcome", ["success", "fallback", "timeout", "missing_usage"])
def test_dedicated_classifier_every_send_has_ledger_attempt(ledger, monkeypatch, outcome):
    funded(ledger)
    calls = []

    class Rejected(Exception):
        status_code = 400

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = NS(completions=NS(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            if outcome == "fallback" and len(calls) == 1:
                raise Rejected("synthetic rejection")
            if outcome == "timeout":
                raise TimeoutError("SYNTHETIC_PRIVATE_TEXT")
            return response('{"flagged":false,"confidence":0.2}', usage=outcome != "missing_usage")

    monkeypatch.setattr("app.agent.injection_guard.OpenAI", Client)
    monkeypatch.setattr(settings, "injection_guard_enabled", True)
    guard = InjectionGuard()
    guard._initialized = True
    guard._llm = SovereignLLMClient("http://sovereign.invalid/v1", "test-classifier")
    with operation(ledger, SCOPE, "classifier"):
        verdict = guard.check("SYNTHETIC_PRIVATE_TEXT")
    assert len(calls) == (2 if outcome == "fallback" else 1)
    summary = ledger.summary()
    assert summary["states"].get("unknown", 0) == (
        1 if outcome in {"timeout", "missing_usage", "fallback"} else 0
    )
    assert "SYNTHETIC_PRIVATE_TEXT" not in str(verdict)
    if outcome == "timeout":
        assert verdict.status == "error"


def test_classifier_budget_denial_does_not_fail_open(ledger, monkeypatch):
    calls = []
    client = SovereignLLMClient.__new__(SovereignLLMClient)
    client.model = "test"
    client._client = NS(chat=NS(completions=NS(create=lambda **kw: calls.append(kw))))
    guard = InjectionGuard()
    guard._initialized = True
    guard._llm = client
    monkeypatch.setattr(settings, "injection_guard_enabled", True)
    with operation(ledger, SCOPE, "classifier"), pytest.raises(ControlError):
        guard.check("synthetic")
    assert calls == []


job_boundary = job_boundary_fixture
worker = worker_fixture


@pytest.mark.parametrize("update", [{"revision": 2}, {"generation": "regranted-2"}])
def test_saved_worker_receipt_protects_history_recovery_and_references(saved_worker, update):
    from app.conversations.models import Turn
    from tests.test_saved_jobs import submit as saved_submit

    client, store, repo, identity, cid, adapter, _, calls, path, auth = saved_worker
    job_id = saved_submit(saved_worker)
    assert run_one(store.admission, adapter)
    url = "/api/conversations/" + cid
    previous = client.get(url + "/messages")
    assert previous.status_code == 200 and "_authorization" not in previous.text
    with repo.sessions() as session:
        turn = session.get(Turn, (cid, job_id))
        assert turn.response["_authorization"]["generation"] == "fixture-1"
    change(path, auth, **update)
    assert client.get(url + "/messages").status_code == 404
    assert client.get(url + "/jobs/by-request/saved_request_001").status_code == 404
    body = {
        "participant_id": "gh:1",
        "exercise_id": "echo-1",
        "exercise_version": "v1",
        "request_id": "saved_request_002",
        "expected_revision": 2,
        "message": "Explain this",
        "stance": "peer",
        "reply_to": {"conversation_id": cid, "request_id": job_id},
    }
    denied_reference = client.post(url + "/jobs", json=body)
    assert denied_reference.status_code == 409, denied_reference.text
    assert len(calls) == 3


from tests.test_saved_jobs import saved_worker as saved_worker_fixture

saved_worker = saved_worker_fixture
