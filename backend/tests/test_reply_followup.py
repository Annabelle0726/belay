# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest

# Imported fixtures deliberately use pytest name-based injection.
# ruff: noqa: F811
from app.controls.worker import run_one
from tests.http_auth import token
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_jobs_http import BODY, job_boundary  # noqa: F401
from tests.test_jobs_worker import worker  # noqa: F401
from tests.test_saved_jobs import body as saved_body
from tests.test_saved_jobs import saved_worker  # noqa: F401
from tests.test_saved_jobs import submit as saved_submit


def test_controlled_reply_reference_is_owned_and_resolved(worker):
    client, store, _, _, adapter, _, calls = worker
    first = client.post("/api/sol/jobs", json={**BODY, "stance": "control"})
    assert first.status_code == 202
    assert run_one(store.admission, adapter)
    follow = {
        **BODY,
        "request_id": "followup_request_002",
        "reply_to": {"request_id": BODY["request_id"]},
        "recent": [{"who": "student", "text": "?"}],
    }
    admitted = client.post("/api/sol/jobs", json=follow)
    assert admitted.status_code == 202, admitted.text
    assert client.post("/api/sol/jobs", json=follow).json() == admitted.json()
    assert run_one(store.admission, adapter)
    result = client.get("/api/sol/jobs/" + admitted.json()["id"]).json()["result"]
    assert "which part" in result["message"].lower()
    assert result["reply_to"]["request_id"] == BODY["request_id"]
    assert calls == []
    assert (
        client.post(
            "/api/sol/jobs",
            json={**follow, "request_id": "foreign_request_003"},
            headers={"Authorization": "Bearer " + token("other")},
        ).status_code
        == 409
    )


def test_missing_reference_is_not_admitted(worker):
    client, store, _, _, adapter, _, calls = worker
    response = client.post(
        "/api/sol/jobs", json={**BODY, "reply_to": {"request_id": "missing_reply_001"}}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reply_unavailable"
    assert not run_one(store.admission, adapter)
    assert calls == []


@pytest.mark.parametrize(
    "question", ["Why did you choose that approach?", "I meant a category mean, not a row count."]
)
def test_specific_followup_reaches_existing_model_context_with_new_run_separate(worker, question):
    client, store, _, _, adapter, _, calls = worker
    client.post("/api/sol/jobs", json={**BODY, "stance": "control"})
    assert run_one(store.admission, adapter)
    response = client.post(
        "/api/sol/jobs",
        json={
            **BODY,
            "request_id": "specific_followup_002",
            "stance": "peer",
            "reply_to": {"request_id": BODY["request_id"]},
            "source": "new code",
            "result": {
                "ok": False,
                "error": "ValueError: new run",
                "pack": {"execution_status": "student_error"},
            },
            "recent": [{"who": "student", "text": question}],
        },
    )
    assert response.status_code == 202
    assert run_one(store.admission, adapter)
    assert len(calls) == 3
    user = calls[1]["messages"][1]["content"]
    assert "quoted_prior_reply" in user and BODY["request_id"] in user
    assert question in user and "ValueError: new run" in user
    assert "do not infer" in calls[1]["messages"][0]["content"]
    result = client.get("/api/sol/jobs/" + response.json()["id"]).json()["result"]
    assert result["message"] and result["reply_to"]["request_id"] == BODY["request_id"]
    assert "confidence" not in result


def test_expired_quote_before_worker_blocks_execution_without_replay(worker):
    client, store, _, _, adapter, _, calls = worker
    client.post("/api/sol/jobs", json={**BODY, "stance": "control"})
    run_one(store.admission, adapter)
    # Submit near the original result expiry; it expires while this request waits.
    store.ledger.clock = lambda: 399.0
    response = client.post(
        "/api/sol/jobs",
        json={
            **BODY,
            "request_id": "expires_followup_002",
            "reply_to": {"request_id": BODY["request_id"]},
        },
    )
    assert response.status_code == 202
    store.ledger.clock = lambda: 401.0
    assert run_one(store.admission, adapter)
    result = client.get("/api/sol/jobs/" + response.json()["id"]).json()
    assert result["state"] == "failed" and result["reason"] == "reply_unavailable"
    assert calls == []


def test_saved_reference_survives_history_restore_and_duplicate_submission(saved_worker):
    env = saved_worker
    client, store, repo, identity, cid, adapter, _, calls, _, _ = env
    original = saved_submit(env, payload={**saved_body(), "stance": "control"})
    assert run_one(store.admission, adapter)
    quote = {"conversation_id": cid, "request_id": original}
    follow = {
        **saved_body(),
        "request_id": "saved_followup_002",
        "expected_revision": 2,
        "message": "?",
        "reply_to": quote,
    }
    job = saved_submit(env, payload=follow)
    assert saved_submit(env, payload=follow) == job
    assert run_one(store.admission, adapter)
    history = repo.history(identity, cid)["messages"]
    assert len(history) == 4
    assert history[2]["reply_to"]["request_id"] == original
    assert "which part" in history[3]["text"].lower()
    assert calls == []
    assert repo.reply(identity, cid, original)["text"] == history[1]["text"]
    repo.delete(identity, cid)
    response = client.get(f"/api/conversations/{cid}/jobs/by-request/saved_followup_002")
    assert response.status_code in (403, 404)


def test_quote_revocation_before_dispatch_blocks_without_model_calls(worker):
    client, store, path, auth, adapter, _, calls = worker
    client.post("/api/sol/jobs", json={**BODY, "stance": "control"})
    assert run_one(store.admission, adapter)
    response = client.post(
        "/api/sol/jobs",
        json={
            **BODY,
            "request_id": "revoked_followup_002",
            "reply_to": {"request_id": BODY["request_id"]},
        },
    )
    assert response.status_code == 202
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    assert run_one(store.admission, adapter)
    assert calls == []
    assert client.get("/api/sol/jobs/" + response.json()["id"]).status_code == 404


def test_saved_quote_cannot_cross_retention_scopes(saved_worker):
    env = saved_worker
    client, store, _, _, cid, adapter, _, calls, _, _ = env
    original = saved_submit(env, payload={**saved_body(), "stance": "control"})
    assert run_one(store.admission, adapter)
    from app.controls.contracts import ControlError

    with pytest.raises(ControlError, match="reply_unavailable"):
        store.submit(
            env[3],
            "cross_scope_002",
            {**BODY, "reply_to": {"conversation_id": cid, "request_id": original}},
            "sol",
        )
    assert not run_one(store.admission, adapter)
    assert calls == []


def test_long_quote_and_new_error_remain_separate():
    from app.agent.context import build_context
    from app.agent.glass_box import student_glass_box
    from app.agent.reply_context import reply_metadata

    text = "Historical reply. " * 1000
    quote = {
        **reply_metadata({"request_id": "long_reply"}, text),
        "text": text,
        "original_evidence": None,
    }
    payload = {
        "stance": "control",
        "exercise": {
            "title": "Test",
            "concept": "loop",
            "goalText": "Practice",
            "prompt": "Explain",
        },
        "_reply_context": quote,
        "reply_to": {"request_id": "long_reply"},
        "source": "new source",
        "result": {
            "ok": False,
            "error": "ValueError: new run",
            "pack": {"execution_status": "student_error"},
        },
    }
    ctx = build_context(payload, {}, 0)
    assert len(ctx["quoted_prior_reply"]["text"]) == 6000
    assert ctx["quoted_prior_reply"]["truncated"] is True
    assert ctx["quoted_prior_reply"]["original_evidence"] is None
    assert len(quote["excerpt"]) == 360
    assert ctx["last_result"]["error"] == "ValueError: new run"
    evidence = student_glass_box({"intervention": "diagnose"}, payload)["evidence"]
    assert "supplied with this request" in evidence
    assert "ValueError" not in ctx["quoted_prior_reply"]["text"]
