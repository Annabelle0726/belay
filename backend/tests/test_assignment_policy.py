# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic trusted grants; no platform, model service, or deployment database."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.auth import AssignmentGrant
from app.conversations.models import Turn
from tests.http_auth import token
from tests.test_auth_isolation import boundary as boundary_fixture
from tests.test_conversation_http import http_dialogue as http_dialogue_fixture
from tests.test_conversations import dialogue as dialogue_fixture

boundary = boundary_fixture
dialogue = dialogue_fixture
http_dialogue = http_dialogue_fixture

PAIRS = [(mode, stance) for mode in ["study", "teach"] for stance in ["peer", "oracle", "control"]]


def grant(pairs=None, **changes):
    return {
        "version": "v1",
        "generation": "grant-1",
        "policy_revision": 1,
        "allowed_pairs": [
            {"mode": m, "stance": s} for m, s in (pairs if pairs is not None else PAIRS)
        ],
        **changes,
    }


def headers(subject="subject-a"):
    return {"Authorization": "Bearer " + token(subject)}


def install(path, grants, policy, subject="subject-a"):
    grants["subjects"][subject][0]["assignments"]["echo-1"] = policy
    path.write_text(json.dumps(grants), encoding="utf-8")


def released():
    return {
        "affective_state": "curious",
        "affect_reasoning": "",
        "confidence": 0.5,
        "intervention": "observe",
        "planner_note": "",
        "self_critique": "",
        "governance": "none",
        "memory": {"grasped": [], "shaky": []},
        "message": "Released explanation",
        "check_question": None,
    }


@pytest.mark.parametrize("edge", ["/api/sol/turn", "/quad/v1/turn"])
@pytest.mark.parametrize("mode,stance", PAIRS)
@pytest.mark.parametrize("legacy", [False, True])
def test_pairs_are_authorized_not_cartesian(boundary, monkeypatch, edge, mode, stance, legacy):
    client, _, _, path, grants = boundary
    allowed = [("study", "peer")] if legacy else [("study", "peer"), ("teach", "oracle")]
    install(path, grants, "v1" if legacy else grant(allowed))
    from app import main
    from app.integrations.quad import router

    dispatched = []

    def tutor(payload, llm, store):
        dispatched.append((payload["mode"], payload["stance"]))
        return released()

    monkeypatch.setattr(main, "run_turn", tutor)
    monkeypatch.setattr(router, "run_turn", tutor)
    response = client.post(
        edge,
        headers=headers(),
        json={
            "exercise_id": "echo-1",
            "participant_id": "gh:1",
            "pseudo_id": "gh:1",
            "mode": mode,
            "stance": stance,
        },
    )
    assert response.status_code == (200 if (mode, stance) in allowed else 404), response.text
    assert dispatched == ([(mode, stance)] if (mode, stance) in allowed else [])


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"version": "v1"},
        {"version": "v1", "allowed_pairs": []},
        grant(policy_revision=True),
        grant(policy_revision=0),
        grant(allowed_pairs=None),
        grant(allowed_pairs=[{"mode": "study"}]),
        grant(allowed_pairs=[{"mode": "study", "stance": "other"}]),
        grant(generation=""),
        grant(extra="ignored?"),
    ],
)
def test_malformed_object_policy_never_migrates(boundary, bad):
    client, _, calls, path, grants = boundary
    install(path, grants, bad)
    response = client.post(
        "/api/sol/turn", headers=headers(), json={"participant_id": "gh:1", "exercise_id": "echo-1"}
    )
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize("edge", ["/api/sol/turn", "/quad/v1/turn"])
@pytest.mark.parametrize("change", ["narrow", "revoke", "regrant", "malformed"])
def test_change_after_first_inference_stops_more_calls_and_delivery(
    boundary, monkeypatch, edge, change
):
    client, _, _, path, grants = boundary
    install(path, grants, grant())
    from app import main
    from app.integrations.quad import router

    calls = []

    def dispatch(**kwargs):
        calls.append(kwargs["role"])
        policy = grant([("study", "peer")], policy_revision=2)
        if change == "revoke":
            grants["subjects"]["subject-a"][0]["assignments"] = {}
            path.write_text(json.dumps(grants))
        else:
            if change == "regrant":
                policy = grant(generation="grant-2")
            if change == "malformed":
                policy = {}
            install(path, grants, policy)
        return {}

    provider = SimpleNamespace(name="synthetic", json=dispatch)
    monkeypatch.setattr(main, "_llm", lambda: provider)

    # Quad caches its injected factory; rebuild its wiring with this synthetic provider.
    # The boundary's Quad factory returns None, so the tutor uses a guarded adapter below.
    def tutor(payload, llm, store):
        from app.pedagogy import AuthorizedProvider

        guarded = AuthorizedProvider(provider)
        guarded.json(role="first")
        guarded.json(role="second")
        return released()

    monkeypatch.setattr(main, "run_turn", tutor)
    monkeypatch.setattr(router, "run_turn", tutor)
    response = client.post(
        edge,
        headers=headers(),
        json={
            "participant_id": "gh:1",
            "pseudo_id": "gh:1",
            "exercise_id": "echo-1",
            "mode": "teach",
            "stance": "oracle",
        },
    )
    assert response.status_code in [404, 503]
    assert "Released explanation" not in response.text
    assert calls == ["first"]


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
@pytest.mark.parametrize("mode,stance", PAIRS)
def test_saved_pairs_checked_before_tutor(http_dialogue, prefix, mode, stance):
    from tests.test_conversation_http import auth, create

    client, _, _, _, calls, path, grants = http_dialogue
    install(path, grants, grant([("study", "peer"), ("teach", "oracle")]), "one")
    cid = create(client, prefix).json()["conversation_id"]
    response = client.post(
        prefix + "/conversations/" + cid + "/turns",
        headers=auth(),
        json={
            "request_id": "turn-1",
            "expected_revision": 0,
            "message": "Explain",
            "mode": mode,
            "stance": stance,
        },
    )
    allowed = (mode, stance) in [("study", "peer"), ("teach", "oracle")]
    assert response.status_code == (200 if allowed else 404), response.text
    assert len(calls) == int(allowed)


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
@pytest.mark.parametrize("change", ["narrow", "regrant", "legacy"])
def test_saved_replay_and_history_respect_current_policy(http_dialogue, prefix, change):
    from tests.test_conversation_http import auth, create

    client, store, _, _, calls, path, grants = http_dialogue
    install(path, grants, grant(), "one")
    cid = create(client, prefix).json()["conversation_id"]
    url = prefix + "/conversations/" + cid
    body = {
        "request_id": "turn-1",
        "expected_revision": 0,
        "message": "Explain",
        "mode": "teach",
        "stance": "oracle",
    }
    assert client.post(url + "/turns", headers=auth(), json=body).status_code == 200
    assert "_authorization" not in client.get(url + "/messages", headers=auth()).text
    if change == "legacy":
        with store.sessions.begin() as session:
            turn = session.scalars(select(Turn)).one()
            turn.response = {k: v for k, v in turn.response.items() if k != "_authorization"}
    else:
        install(
            path,
            grants,
            grant([("study", "peer")], policy_revision=2)
            if change == "narrow"
            else grant(generation="grant-2"),
            "one",
        )
    assert client.post(url + "/turns", headers=auth(), json=body).status_code == 404
    assert client.get(url + "/messages", headers=auth()).status_code == 404
    assert len(calls) == 1
    assert client.delete(url, headers=auth()).status_code == 204


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
def test_saved_policy_change_before_publication_is_not_released(http_dialogue, monkeypatch, prefix):
    from app.conversations import router
    from tests.test_conversation_http import auth, create

    client, store, _, consent, _, path, grants = http_dialogue
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.packs._skeleton.pack import SkeletonPack

    install(path, grants, grant(), "one")

    def tutor(payload, llm, course):
        install(path, grants, grant([("study", "peer")], policy_revision=2), "one")
        return released()

    app = FastAPI()
    app.include_router(
        router.build_router(
            prefix,
            consent,
            SkeletonPack(),
            lambda: None,
            engine=store.engine,
            policy=store.policy,
            tutor=tutor,
        )
    )
    client = TestClient(app)
    cid = create(client, prefix).json()["conversation_id"]
    response = client.post(
        prefix + "/conversations/" + cid + "/turns",
        headers=auth(),
        json={
            "request_id": "turn-1",
            "expected_revision": 0,
            "message": "Explain",
            "mode": "teach",
            "stance": "oracle",
        },
    )
    assert response.status_code == 404
    with store.sessions() as session:
        turn = session.scalars(select(Turn)).one()
        assert turn.status == "failed" and turn.response is None


def test_class_policy_does_not_authorize_another_class(boundary):
    client, _, calls, path, grants = boundary
    install(path, grants, grant())
    grants["subjects"]["subject-class"][0]["assignments"]["echo-1"] = "v1"
    path.write_text(json.dumps(grants))
    response = client.post(
        "/api/sol/turn",
        headers=headers("subject-class"),
        json={
            "participant_id": "gh:1",
            "exercise_id": "echo-1",
            "mode": "teach",
            "stance": "oracle",
        },
    )
    assert response.status_code == 404 and calls == []


def test_empty_pairs_is_explicit_denial():
    assert not AssignmentGrant.model_validate(grant([])).permits("study", "peer")


@pytest.mark.parametrize("malformed", [False, True])
def test_sdk_fallback_and_repair_recheck_before_another_dispatch(monkeypatch, malformed):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app import pedagogy
    from app.agent.llm import OpenAICompatProvider
    from app.config import settings

    calls = []

    def check():
        if calls:
            raise HTTPException(404, "resource unavailable")

    def create(**kwargs):
        calls.append(kwargs)
        if not malformed:
            raise ValueError("synthetic format rejection")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="not JSON"))]
        )

    provider = object.__new__(OpenAICompatProvider)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(settings, "openai_reasoning", False)
    marker = pedagogy._check.set(check)
    try:
        with pytest.raises(HTTPException) as error:
            provider.json(role="reasoner", tier="fast", system="Synthetic", user="Synthetic")
        assert error.value.status_code == 404
        assert len(calls) == 1
    finally:
        pedagogy._check.reset(marker)


def test_saved_permission_receipt_counts_toward_retention_size(http_dialogue):
    from app.conversations.bounds import wire_size
    from app.conversations.models import Conversation, Message
    from tests.test_conversation_http import auth, create

    client, store, _, _, _, _, _ = http_dialogue
    cid = create(client).json()["conversation_id"]
    result = client.post(
        "/api/conversations/" + cid + "/turns",
        headers=auth(),
        json={"request_id": "size-1", "expected_revision": 0, "message": "Explain"},
    )
    assert result.status_code == 200
    with store.sessions() as session:
        turn = session.scalars(select(Turn)).one()
        row = session.get(Conversation, cid)
        messages = session.scalars(select(Message)).all()
        assert row.byte_count == sum(m.byte_count for m in messages) + wire_size(turn.response)
        assert "_authorization" in turn.response
        assert "_authorization" not in result.json()


def test_authorized_control_does_not_construct_a_model(boundary, monkeypatch):
    from app import main

    client, _, _, path, grants = boundary
    install(path, grants, grant([("study", "control")]))

    def forbidden():
        raise AssertionError("control must not construct a model client")

    monkeypatch.setattr(main, "_llm", forbidden)
    result = client.post(
        "/api/sol/turn",
        headers=headers(),
        json={"participant_id": "gh:1", "exercise_id": "echo-1", "stance": "control"},
    )
    assert result.status_code == 200, result.text
