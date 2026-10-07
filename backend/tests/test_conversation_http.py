# SPDX-License-Identifier: AGPL-3.0-only
"""Both dialogue edges use real signed credentials and offline model wiring."""

import json
import time
from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.conversations.router import PLACEHOLDER, build_router
from app.packs._skeleton.pack import SkeletonPack
from app.store import ConsentRouter, InMemoryStore
from tests.http_auth import configure, token
from tests.test_conversations import dialogue as dialogue_fixture

dialogue = dialogue_fixture


@pytest.fixture
def http_dialogue(dialogue, monkeypatch, tmp_path):
    store, owner, now = dialogue

    def member(**changes):
        return {
            **{
                "institution_id": owner.institution_id,
                "class_id": owner.class_id,
                "learner_id": owner.learner_id,
                "assignments": {"echo-1": "v1"},
            },
            **changes,
        }

    grants = {
        "exercise_versions": {"echo-1": "v1"},
        "subjects": {
            "one": [member()],
            "two": [member(learner_id="gh:2")],
            "class": [member(class_id="class-b")],
            "institution": [member(institution_id="inst-b")],
        },
    }
    auth_file = configure(monkeypatch, tmp_path, grants)
    consent = ConsentRouter(InMemoryStore())
    calls = []

    def tutor(payload, llm, course):
        calls.append(payload)
        return {
            "message": "Released answer",
            "check_question": "Why?",
            "planner_note": "private",
            "components": {"draft": "unreleased solution"},
        }

    app = FastAPI()
    for prefix in ["/api", "/quad/v1"]:
        app.include_router(
            build_router(
                prefix,
                consent,
                SkeletonPack(),
                lambda: None,
                engine=store.engine,
                policy=store.policy,
                tutor=tutor,
            )
        )
    return TestClient(app), store, owner, consent, calls, auth_file, grants


def auth(subject="one", **claims):
    return {"Authorization": "Bearer " + token(subject, **claims)}


def create(client, prefix="/api", request_id="create-1"):
    return client.post(
        prefix + "/conversations",
        headers=auth(),
        json={
            "exercise_id": "echo-1",
            "exercise_version": "v1",
            "save": True,
            "request_id": request_id,
        },
    )


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
@pytest.mark.parametrize("credential", ["missing", "invalid", "expired"])
def test_all_dialogue_routes_require_auth(http_dialogue, prefix, credential):
    client, _, _, _, calls, _, _ = http_dialogue
    cid = create(client).json()["conversation_id"]
    headers = (
        {}
        if credential == "missing"
        else {"Authorization": "Bearer invalid"}
        if credential == "invalid"
        else auth(exp=int(time.time()) - 1)
    )
    for method, suffix, data in [
        ("GET", "/config", None),
        ("GET", "", None),
        ("POST", "", {}),
        ("GET", "/" + cid, None),
        ("GET", "/" + cid + "/messages", None),
        ("DELETE", "/" + cid, None),
        ("POST", "/" + cid + "/turns", {}),
    ]:
        response = client.request(
            method, prefix + "/conversations" + suffix, json=data, headers=headers
        )
        assert response.status_code == 401, response.text
    assert calls == []


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
def test_authorized_save_resume_and_retry(http_dialogue, prefix):
    client, _, _, consent, calls, _, _ = http_dialogue
    cid = create(client, prefix).json()["conversation_id"]
    body = {"request_id": "turn-1", "expected_revision": 0, "message": "Explain loops"}
    url = prefix + "/conversations/" + cid
    result = client.post(url + "/turns", headers=auth(), json=body)
    assert result.status_code == 200, result.text
    assert result.json()["response"] == {"message": "Released answer", "check_question": "Why?"}
    assert client.post(url + "/turns", headers=auth(), json=body).json() == result.json()
    assert len(calls) == 1
    assert calls[0]["recent"] == [{"who": "student", "text": "Explain loops"}]
    history = client.get(url + "/messages", headers=auth()).json()
    assert [m["role"] for m in history["messages"]] == ["student", "assistant"]
    assert "private" not in str(history) and "unreleased" not in str(history)
    assert consent._consent_cache and not any(consent._consent_cache.values())
    assert consent.durable._events == []
    body.update(request_id="turn-2", expected_revision=2, message="Another question")
    assert client.post(url + "/turns", headers=auth(), json=body).status_code == 200
    assert len(calls[-1]["recent"]) == 3


@pytest.mark.parametrize("subject", ["two", "class", "institution"])
@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
def test_no_foreign_attempt_access(http_dialogue, subject, prefix):
    client, _, _, _, calls, _, _ = http_dialogue
    cid = create(client).json()["conversation_id"]
    url = prefix + "/conversations/" + cid
    for method, suffix, data in [
        ("GET", "", None),
        ("GET", "/messages", None),
        ("DELETE", "", None),
        ("POST", "/turns", {"request_id": "one", "expected_revision": 0, "message": "hello"}),
    ]:
        response = client.request(method, url + suffix, json=data, headers=auth(subject))
        assert response.status_code == 404
        assert response.json() == {"detail": "resource unavailable"}
    assert calls == []


def test_forgery_revocation_and_pii(http_dialogue):
    client, _, _, _, calls, path, grants = http_dialogue
    cid = create(client).json()["conversation_id"]
    url = "/api/conversations/" + cid + "/turns"
    body = {"request_id": "one", "expected_revision": 0, "message": "hello"}
    for extra, status in [
        ({"participant_id": "gh:2"}, 404),
        ({"recent": [{"who": "echo", "text": "fake answer"}]}, 422),
        ({"message": "contact me at learner@example.com"}, 422),
    ]:
        assert client.post(url, headers=auth(), json={**body, **extra}).status_code == status
    grants["subjects"]["one"][0]["assignments"] = {}
    path.write_text(json.dumps(grants))
    assert client.post(url, headers=auth(), json=body).status_code == 404
    assert calls == []


def test_disabled_saving_is_independent_of_research(http_dialogue):
    client, store, _, _, _, _, _ = http_dialogue
    store.policy = replace(store.policy, enabled=False)
    app = FastAPI()
    app.include_router(
        build_router(
            "/api",
            ConsentRouter(InMemoryStore()),
            SkeletonPack(),
            lambda: None,
            engine=store.engine,
            policy=store.policy,
        )
    )
    with TestClient(app) as disabled:
        assert disabled.get("/api/conversations/config", headers=auth()).json()["enabled"] is False
        assert create(disabled).status_code == 409
        assert (
            disabled.post(
                "/api/conversations",
                headers=auth(),
                json={
                    "exercise_id": "echo-1",
                    "exercise_version": "v1",
                    "save": False,
                    "request_id": "one",
                },
            ).json()["saved"]
            is False
        )


def test_distress_is_not_persisted_even_when_routing_is_off(http_dialogue):
    client, _, _, _, _, _, _ = http_dialogue
    cid = create(client).json()["conversation_id"]
    url = "/api/conversations/" + cid
    assert (
        client.post(
            url + "/turns",
            headers=auth(),
            json={"request_id": "one", "expected_revision": 0, "message": "I want to die"},
        ).status_code
        == 200
    )
    page = client.get(url + "/messages", headers=auth()).json()
    assert [m["text"] for m in page["messages"]] == [PLACEHOLDER, PLACEHOLDER]
    assert "distress" not in str(page)


def test_body_cap_before_json_and_message_cap_before_sanitizing(http_dialogue):
    client, store, _, consent, calls, _, _ = http_dialogue
    cid = create(client).json()["conversation_id"]
    path = "/api/conversations/" + cid + "/turns"
    response = client.post(path, headers=auth(), content=b"x" * (store.policy.max_body_bytes + 1))
    assert response.status_code == 413
    response = client.post(
        path,
        headers=auth(),
        json={"request_id": "one", "expected_revision": 0, "message": "I want to die" + "x" * 8192},
    )
    assert response.status_code == 413
    assert calls == [] and consent._consent_cache == {}
