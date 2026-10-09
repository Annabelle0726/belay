# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.controls import jobs_http
from app.controls.data import ExecutionData, data
from app.packs._skeleton.pack import SkeletonPack
from tests.http_auth import token
from tests.test_execution_grants import grant_boundary  # noqa: F401


@pytest.fixture
def job_boundary(ledger, grant_boundary, monkeypatch):  # noqa: F811
    _, path, auth = grant_boundary
    store = ExecutionData(ledger, "test", Fernet.generate_key())
    monkeypatch.setattr(jobs_http, "execution_store", lambda: store)
    app = FastAPI()
    for prefix in ("/api/sol/jobs", "/quad/v1/jobs"):
        app.include_router(jobs_http.build_jobs_router(prefix, SkeletonPack()))
    client = TestClient(app, headers={"Authorization": "Bearer " + token("original")})
    return client, store, path, auth


BODY = dict(
    request_id="logical_request_001",
    participant_id="gh:1",
    exercise_id="echo-1",
    exercise_version="v1",
    stance="control",
)


@pytest.mark.parametrize("prefix", ["/api/sol/jobs", "/quad/v1/jobs"])
def test_signed_http_admission_and_scoped_recovery(job_boundary, prefix):
    client, store, _, _ = job_boundary
    config = client.get(prefix + "/config")
    assert config.status_code == 200 and config.json()["assignments"] == {"echo-1": "v1"}
    first = client.post(prefix, json=BODY)
    assert first.status_code == 202 and first.json()["state"] == "queued"
    assert first.headers["Cache-Control"] == "no-store"
    assert client.post(prefix, json=BODY).json() == first.json()
    recovered = client.get(prefix + "/by-request/" + BODY["request_id"])
    assert recovered.json()["id"] == first.json()["id"]
    assert recovered.json()["result"] is None
    assert client.post(prefix, json={**BODY, "source": "changed"}).status_code == 409
    foreign = client.get(
        prefix + "/" + first.json()["id"], headers={"Authorization": "Bearer " + token("other")}
    )
    assert foreign.status_code == 404  # same learner, different original principal
    with store.ledger.transaction() as conn:
        assert len(list(conn.execute(select(data)))) == 1


def test_missing_forged_and_revoked_identity_cannot_use_jobs(job_boundary):
    client, _, path, auth = job_boundary
    route = "/api/sol/jobs"
    assert client.post(route, json={**BODY, "participant_id": "gh:999"}).status_code == 404
    assert (
        client.post(route, json=BODY, headers={"Authorization": "Bearer forged"}).status_code == 401
    )
    response = client.post(route, json=BODY)
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    assert client.get(route + "/" + response.json()["id"]).status_code == 404


def test_body_bound(job_boundary):
    client, _, _, _ = job_boundary
    assert client.post("/api/sol/jobs", content=b"x" * (1048576 + 1)).status_code == 413


def test_unconfigured_jobs_fail_closed(monkeypatch):
    from app.controls.contracts import ControlError

    monkeypatch.setattr(settings, "controls_jobs_enabled", False)
    with pytest.raises(ControlError, match="jobs_disabled"):
        jobs_http.execution_store()
    monkeypatch.setattr(settings, "controls_jobs_enabled", True)
    monkeypatch.setattr(settings, "controls_mode", "development_bypass")
    with pytest.raises(ControlError, match="invalid_controls_mode"):
        jobs_http.execution_store()
