# SPDX-License-Identifier: AGPL-3.0-only
"""Signed real code runner followed by controlled feedback with a model stub."""

import json

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.controls import jobs_http
from app.controls.admission import jobs
from app.controls.contracts import Limits
from app.controls.data import ExecutionData
from app.controls.jobs_worker import AskAdapter
from app.controls.local_demo import DemoProvider
from app.controls.worker import run_one
from app.packs.datascience import DataSciencePack
from app.store import ConsentRouter, InMemoryStore
from conftest import controls_policy
from tests.http_auth import configure, token


@pytest.fixture
def run_feedback(ledger, monkeypatch, tmp_path):
    import app.main as main

    monkeypatch.setenv("TUTOR_PACK", "datascience")
    member = dict(
        institution_id="i", class_id="c", learner_id="gh:1", assignments={"ds-foundations": "v1"}
    )
    auth = dict(
        exercise_versions={"ds-foundations": "v1"},
        subjects={"original": [member], "other": [member]},
    )
    path = configure(monkeypatch, tmp_path, auth)
    monkeypatch.setattr(settings, "controls_mode", "enforced")
    monkeypatch.setattr(settings, "controls_jobs_enabled", True)
    store = ExecutionData(ledger, "test", Fernet.generate_key())
    ledger.update_policy(
        controls_policy(
            version="run-feedback", deployment=Limits(tokens=1000000, runs=10, wall_ms=300000)
        )
    )
    monkeypatch.setattr(jobs_http, "execution_store", lambda: store)
    pack = DataSciencePack()
    router = ConsentRouter(InMemoryStore())
    monkeypatch.setattr(main, "_pack", pack)
    monkeypatch.setattr(main, "_router", router)
    app = FastAPI()
    app.add_exception_handler(main.ControlError, main.control_error)
    app.router.routes.extend(r for r in main.app.routes if getattr(r, "path", "") == "/api/run")
    app.include_router(jobs_http.build_jobs_router("/api/sol/jobs", pack))
    client = TestClient(app, headers={"Authorization": "Bearer " + token("original")})
    adapter = AskAdapter(store, router, pack, DemoProvider)
    return client, store, adapter, pack, path, auth


SOURCE = 'print("isolated code output")\nresult = {}'
RUN = dict(participant_id="gh:1", exercise_id="ds-foundations", source=SOURCE)


def test_signed_real_run_then_one_feedback_job_and_accounting(run_feedback):
    client, store, adapter, _, _, _ = run_feedback
    result = client.post("/api/run", json=RUN)
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True and result.json()["goalMet"] is False
    assert "isolated code output" in result.json()["pack"]["stdout"]
    assert store.ledger.summary()["consumed"]["runs"] == 1
    body = dict(
        **RUN,
        result=result.json(),
        request_id="automatic_run_feedback_001",
        exercise_version="v1",
        event="run",
        stance="peer",
        recent=[{"who": "student", "text": "Help me understand the result of this run."}],
    )
    first = client.post("/api/sol/jobs", json=body)
    assert first.status_code == 202, first.text
    assert client.post("/api/sol/jobs", json=body).json() == first.json()
    assert run_one(store.admission, adapter)
    assert not run_one(store.admission, adapter)
    status = client.get("/api/sol/jobs/by-request/" + body["request_id"])
    assert status.json()["state"] == "completed", status.text
    assert "Local model stub" in status.json()["result"]["message"]
    assert store.ledger.summary()["consumed"]["tokens"] == 45
    with store.ledger.transaction() as conn:
        assert len(conn.execute(select(jobs)).all()) == 1


def test_run_requires_identity_and_keeps_runner_budget(run_feedback):
    client, store, _, _, _, _ = run_feedback
    assert client.post("/api/run", json={**RUN, "participant_id": "gh:other"}).status_code == 404
    store.ledger.update_policy(controls_policy(version="no-runs", deployment=Limits(runs=0)))
    denied = client.post("/api/run", json=RUN)
    assert denied.status_code == 429
    assert store.ledger.summary()["consumed"]["runs"] == 0


def test_original_subject_revoked_after_run_cannot_release_result(run_feedback, monkeypatch):
    client, store, _, pack, path, auth = run_feedback
    original = pack.run

    def revoke(*args):
        result = original(*args)
        del auth["subjects"]["original"]
        path.write_text(json.dumps(auth))
        return result

    monkeypatch.setattr(pack, "run", revoke)
    denied = client.post("/api/run", json=RUN)
    assert denied.status_code == 404
    assert "isolated code output" not in denied.text
    assert store.ledger.summary()["consumed"]["runs"] == 1
