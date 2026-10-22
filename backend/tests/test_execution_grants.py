# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.auth import authorize, execution_grant, recheck_grant
from app.config import settings
from tests.http_auth import configure, token


@pytest.fixture
def grant_boundary(monkeypatch, tmp_path):
    member = dict(
        institution_id="i",
        class_id="c",
        learner_id="gh:1",
        assignments={
            "echo-1": {
                "version": "v1",
                "generation": "fixture-1",
                "policy_revision": 1,
                "allowed_pairs": [
                    {"mode": m, "stance": s}
                    for m in ["study", "teach"]
                    for s in ["peer", "oracle", "control"]
                ],
            }
        },
    )
    auth = dict(
        exercise_versions={"echo-1": "v1"}, subjects={"original": [member], "other": [member]}
    )
    path = configure(monkeypatch, tmp_path, auth)
    app = FastAPI()
    captured = []

    @app.post("/grant", dependencies=[Depends(authorize)])
    def capture(request: Request):
        grant = execution_grant(request.state.identity)
        captured.append(grant)
        return grant.model_dump()

    client = TestClient(app)
    response = client.post(
        "/grant",
        json={"exercise_id": "echo-1"},
        headers={"Authorization": "Bearer " + token("original")},
    )
    assert response.status_code == 200
    return captured[0], path, auth


def test_token_free_check_binds_original_subject(grant_boundary):
    grant, path, auth = grant_boundary
    assert recheck_grant(grant).learner_id == "gh:1"
    assert "original" not in grant.model_dump_json()
    assert "Bearer" not in grant.model_dump_json()
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    with pytest.raises(HTTPException) as error:
        recheck_grant(grant)
    assert error.value.status_code == 404


@pytest.mark.parametrize("change", ["assignment", "deployed_version", "config", "issuer"])
def test_worker_recheck_fails_closed(grant_boundary, monkeypatch, change):
    grant, path, auth = grant_boundary
    if change == "assignment":
        auth["subjects"]["original"][0]["assignments"].clear()
    elif change == "deployed_version":
        auth["exercise_versions"]["echo-1"] = "v2"
    elif change == "issuer":
        monkeypatch.setattr(settings, "auth_issuer", "https://changed.invalid")
    path.write_text("bad JSON" if change == "config" else json.dumps(auth))
    with pytest.raises(HTTPException):
        recheck_grant(grant)
