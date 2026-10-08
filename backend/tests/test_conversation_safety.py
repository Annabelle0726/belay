# SPDX-License-Identifier: AGPL-3.0-only
"""Actual governance output and failure/revocation paths at the saving boundary."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.conversations.router import PLACEHOLDER, build_router, live_signals
from app.core.registry import get_active_pack
from app.store import ConsentRouter, InMemoryStore
from tests.http_auth import configure, token
from tests.test_conversations import dialogue as dialogue_fixture
from tests.test_stance import _SOLUTION_MSG, StubLLM

dialogue = dialogue_fixture


@pytest.mark.parametrize("content", ["learner@example.com", "I want to die", "x" * 513])
def test_live_summaries_screen_sensitive_and_oversize_content(content):
    summary = live_signals({"planner_note": content, "components": {"draft": "hidden"}}, 8192)
    assert content not in str(summary)
    assert "hidden" not in str(summary)


def test_live_summaries_are_bounded_and_ignore_arbitrary_fields():
    released = {
        "message": "released",
        "planner_note": "A small check",
        "confidence": 0.75,
        "memory": {"grasped": ["loops"], "raw": "hidden"},
        "components": {"draft": "hidden", "timings_ms": {"planner_ms": 12, "raw": "hidden"}},
    }
    assert live_signals(released, 1) == {}
    signals = live_signals(released, 8192)
    assert signals["planner_note"] == "A small check"
    assert "hidden" not in str(signals) and "released" not in str(signals)
    assert signals["components"]["timings_ms"] == {"planner_ms": 12}


@pytest.mark.parametrize(
    "scenario", ["released", "failure", "pii-output", "revoked", "delete-during-model", "distress"]
)
def test_governance_and_lifecycle_during_actual_http_turn(
    dialogue, monkeypatch, tmp_path, scenario
):
    store, _, _ = dialogue
    monkeypatch.setenv("TUTOR_PACK", "datascience")
    grants = {
        "exercise_versions": {"ds-foundations": "v1"},
        "subjects": {
            "one": [
                {
                    "institution_id": "inst-a",
                    "class_id": "class-a",
                    "learner_id": "gh:1",
                    "assignments": {"ds-foundations": "v1"},
                }
            ]
        },
    }
    path = configure(monkeypatch, tmp_path, grants)
    headers = {"Authorization": "Bearer " + token("one")}

    class Stub(StubLLM):
        name = "offline"

    llm = Stub(leak=True)
    kwargs = {}
    consent = ConsentRouter(InMemoryStore())
    if scenario == "distress":
        monkeypatch.setattr(settings, "distress_routing_enabled", True)
    if scenario in {"failure", "pii-output", "revoked", "delete-during-model"}:

        def tutor(payload, provider, course):
            if scenario == "failure":
                raise RuntimeError("internal exception must not be returned")
            if scenario == "revoked":
                grants["subjects"]["one"][0]["assignments"] = {}
                path.write_text(json.dumps(grants))
            if scenario == "delete-during-model":
                store.delete(course.identity, cid)
            return {
                "message": "contact learner@example.com" if scenario == "pii-output" else "released"
            }

        kwargs["tutor"] = tutor
    app = FastAPI()
    app.include_router(
        build_router(
            "/api",
            consent,
            get_active_pack(),
            lambda: llm,
            engine=store.engine,
            policy=store.policy,
            **kwargs,
        )
    )
    with TestClient(app) as client:
        cid = client.post(
            "/api/conversations",
            headers=headers,
            json={
                "exercise_id": "ds-foundations",
                "exercise_version": "v1",
                "request_id": "one",
                "save": True,
            },
        ).json()["conversation_id"]
        response = client.post(
            "/api/conversations/" + cid + "/turns",
            headers=headers,
            json={
                "request_id": "turn",
                "expected_revision": 0,
                "message": "I want to die"
                if scenario == "distress"
                else "Help me reason about the data",
            },
        )
        expected = (
            502
            if scenario == "failure"
            else 404
            if scenario in {"revoked", "delete-during-model"}
            else 200
        )
        assert response.status_code == expected, response.text
        if scenario == "revoked":
            grants["subjects"]["one"][0]["assignments"] = {"ds-foundations": "v1"}
            path.write_text(json.dumps(grants))
        history = client.get("/api/conversations/" + cid + "/messages", headers=headers)
        if scenario == "delete-during-model":
            assert history.status_code == 404
        else:
            messages = history.json()["messages"]
            if scenario in {"failure", "revoked"}:
                assert len(messages) == 1 and messages[0]["status"] == "failed"
                assert "internal exception" not in response.text
            elif scenario in {"pii-output", "distress"}:
                assert "live_signals" not in response.json()
                assert messages[-1]["text"] == PLACEHOLDER
                assert "learner@example.com" not in str(messages)
                if scenario == "distress":
                    assert messages[0]["text"] == PLACEHOLDER
                    assert response.json()["unsaved_exchange"] is True
                    assert "study tool" in response.json()["response"]["message"]
            else:
                assert len(messages) == 2
                assert _SOLUTION_MSG not in messages[-1]["text"]
                released = response.json()["response"]
                text = released["message"] + (
                    "\n\n" + released["check_question"] if released.get("check_question") else ""
                )
                assert messages[-1]["text"] == text
                assert llm.seen_systems
        assert consent.durable.export_jsonl() == ""
