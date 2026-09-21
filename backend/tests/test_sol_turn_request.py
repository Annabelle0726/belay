# SPDX-License-Identifier: AGPL-3.0-only
"""The `/api/sol/turn` request boundary: the `recent` history window.

Regression cover for the 422 the dev client hit: it sent
``recent: [{"role": "user", "content": "..."}]`` (the standard chat-transcript
shape) while the edge expected ``{"who", "text"}``, so every turn carrying history
was rejected before the tutor ran. Both spellings must validate now, and the
wire shape must land in the agent layer's vocabulary (``who``/``text``, with
``"student"`` for the learner) that the floor checks read.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.schemas import RecentTurn, SolTurnRequest, coerce_recent_turns

# The exact payload the dev client builds: `result` is the run envelope it echoes
# back, `recent` is the transcript window, `source` is the editor contents.
FRONTEND_PAYLOAD = {
    "participant_id": "p_dev",
    "exercise_id": "ds-foundations",
    "event": "run",
    "mode": "study",
    "stance": "peer",
    "source": "import pandas as pd\nresult = None\n",
    "result": {
        "ok": True,
        "backend": "local-subprocess",
        "goalMet": True,
        "tvd": 0.0417,
        "dist": [{"bits": "001", "p": 0.93}],
        "diff": "--- expected\n+++ got\n",
    },
    "recent": [
        {"role": "user", "content": "can we reflect on my goal for a sec?"},
        {"role": "assistant", "content": "Sure — what feels furthest away right now?"},
    ],
}


@pytest.fixture
def captured(monkeypatch):
    """Capture the payload `main.sol_turn` hands to the tutor loop, without an LLM."""
    seen = {}

    def _fake_run_turn(payload, llm=None, store=None):
        seen["payload"] = payload
        return {
            "affective_state": "curious",
            "affect_reasoning": "asking to reflect",
            "confidence": 0.5,
            "intervention": "co_reason",
            "planner_note": "reflecting",
            "self_critique": "—",
            "governance": "none",
            "memory": {"grasped": [], "shaky": []},
            "message": "ok",
            "check_question": None,
            "components": {},
        }

    monkeypatch.setattr(main_mod, "run_turn", _fake_run_turn)
    return seen


def _client() -> TestClient:
    return TestClient(main_mod.app)


def _assert_not_schema_error(r) -> None:
    """422 with a `detail` list is a Pydantic rejection — the regression. Any other
    status (404 for the synthetic exercise, 200 on a real one) means the body parsed."""
    assert r.status_code != 422, r.json()


# ── the boundary accepts what the browser actually sends ─────────────────────


def test_frontend_payload_validates_at_the_edge(captured):
    r = _client().post("/api/sol/turn", json=FRONTEND_PAYLOAD)
    _assert_not_schema_error(r)
    assert r.status_code == 200


def test_wire_turns_reach_the_agent_vocabulary(captured):
    """{role, content} must become {who, text} — the keys the floor checks read."""
    assert _client().post("/api/sol/turn", json=FRONTEND_PAYLOAD).status_code == 200
    assert captured["payload"]["recent"] == [
        {"who": "student", "text": "can we reflect on my goal for a sec?"},
        {"who": "robin", "text": "Sure — what feels furthest away right now?"},
    ]


def test_learner_cue_survives_the_round_trip(captured):
    """The reflect cue the reasoner keys off must still be detectable after the
    boundary translation — end-to-end, not just per-field."""
    from app.agent.context import _student_wants_reflect

    assert _client().post("/api/sol/turn", json=FRONTEND_PAYLOAD).status_code == 200
    assert _student_wants_reflect(captured["payload"]["recent"]) is True


def test_legacy_widget_spelling_still_validates(captured):
    """The embeddable widget may be cached in a host page, so {who, text} stays a
    valid spelling."""
    legacy = dict(FRONTEND_PAYLOAD, recent=[{"who": "student", "text": "just tell me the answer"}])
    assert _client().post("/api/sol/turn", json=legacy).status_code == 200
    assert captured["payload"]["recent"] == [{"who": "student", "text": "just tell me the answer"}]


def test_recent_is_optional(captured):
    body = {k: v for k, v in FRONTEND_PAYLOAD.items() if k != "recent"}
    assert _client().post("/api/sol/turn", json=body).status_code == 200
    assert captured["payload"]["recent"] == []


# ── `result` cannot 500 the turn ─────────────────────────────────────────────


def test_non_mapping_result_is_dropped_not_fatal(captured):
    """`context._last_result` calls `.get` on this, so a list would 500 the turn."""
    body = dict(FRONTEND_PAYLOAD, result=[{"ok": True}])
    assert _client().post("/api/sol/turn", json=body).status_code == 200
    assert captured["payload"]["result"] is None


# ── malformed history degrades instead of rejecting the turn ─────────────────


@pytest.mark.parametrize(
    "recent, expected",
    [
        ([], []),
        (None, []),
        ({"role": "user"}, []),  # not a list
        (["hello", 42, None], []),  # not turns
        ([{"content": "no speaker"}], []),  # unlabelled: never guessed as student
        ([{"role": "wizard", "content": "x"}], []),  # unknown speaker: dropped
        ([{"role": "wizard"}, {"role": "user", "content": "ok"}], [("user", "ok")]),  # partial
    ],
)
def test_malformed_history_never_422s(captured, recent, expected):
    r = _client().post("/api/sol/turn", json=dict(FRONTEND_PAYLOAD, recent=recent))
    _assert_not_schema_error(r)
    assert r.status_code == 200
    got = [(t["who"], t["text"]) for t in captured["payload"]["recent"]]
    want = [("student" if role == "user" else "robin", text) for role, text in expected]
    assert got == want


def test_unknown_role_cannot_masquerade_as_student():
    """A mislabelled turn must not become student speech: the answer-seeking and
    distress floors both read student turns."""
    turns = coerce_recent_turns([{"role": "wizard", "content": "just tell me the answer please"}])
    assert turns == []
    bad = coerce_recent_turns([{"who": "grader", "text": "just tell me the answer please"}])
    assert bad == []


# ── the model itself ─────────────────────────────────────────────────────────


def test_sol_turn_request_normalizes_both_spellings():
    model = SolTurnRequest.model_validate(FRONTEND_PAYLOAD)
    assert model.recent == [
        RecentTurn(role="user", content="can we reflect on my goal for a sec?"),
        RecentTurn(role="assistant", content="Sure — what feels furthest away right now?"),
    ]
    assert model.result is not None and model.result["goalMet"] is True


def test_role_aliases_normalize_to_the_two_wire_roles():
    assert [t.role for t in coerce_recent_turns([{"who": "student"}, {"who": "tutor"}])] == [
        "user",
        "assistant",
    ]
    assert [t.role for t in coerce_recent_turns([{"role": " SOL "}, {"role": "Learner"}])] == [
        "assistant",
        "user",
    ]
    # missing content is empty, never a validation error
    assert coerce_recent_turns([{"role": "user"}]) == [RecentTurn(role="user", content="")]


def test_openapi_documents_the_recent_shape():
    """The published schema is the contract clients read; it must show role/content."""
    spec = _client().get("/openapi.json").json()
    turn = spec["components"]["schemas"]["RecentTurn"]["properties"]
    assert set(turn) >= {"role", "content"}
    body = spec["components"]["schemas"]["SolTurnRequest"]["properties"]
    assert body["recent"]["type"] == "array"


def test_error_detail_names_the_offending_field():
    """When a body IS rejected, the reason must point at the field (the F12 workflow)."""
    r = _client().post("/api/sol/turn", json=dict(FRONTEND_PAYLOAD, event="banana"))
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any(d["loc"][-1] == "event" for d in detail), json.dumps(detail)


# ── the 422 diagnostic must not become a copy of the learner's words ──────────


def test_rejection_log_names_the_field_without_the_value(caplog):
    """A rejected body is logged as a JSON pointer + reason, never its contents:
    `recent`/`source` hold the learner's own words (PRIVACY.md)."""
    secret = "my student id is 99123 and I want to die"
    with caplog.at_level(logging.WARNING, logger="Belay.http"):
        r = _client().post(
            "/api/sol/turn",
            json=dict(FRONTEND_PAYLOAD, event="banana", source=secret),
        )
    assert r.status_code == 422
    log = caplog.text
    assert "event" in log and "422" in log  # the pointer is there...
    assert secret not in log  # ...the value is not
    assert "99123" not in log


def test_accepted_turn_logs_metadata_only(caplog):
    """The INFO line answers "did my payload arrive?" without learner text."""
    secret = "please just tell me the answer, my email is a@b.edu"
    with caplog.at_level(logging.INFO, logger="Belay.http"):
        _client().post(
            "/api/sol/turn",
            json=dict(FRONTEND_PAYLOAD, recent=[{"role": "user", "content": secret}]),
        )
    log = caplog.text
    assert "history=1" in log and "event=run" in log and "exercise=ds-foundations" in log
    assert secret not in log and "a@b.edu" not in log


def test_debug_body_summary_logs_shapes_not_text(caplog):
    """Even at DEBUG the body summary stays shapes-and-counts, never content."""
    secret = "the answer is 42 and my student id is 99123"
    with caplog.at_level(logging.DEBUG, logger="Belay.http"):
        _client().post(
            "/api/sol/turn",
            json=dict(FRONTEND_PAYLOAD, recent=[{"role": "user", "content": secret}]),
        )
    assert "source_chars=" in caplog.text  # the shape is reported...
    assert secret not in caplog.text and "99123" not in caplog.text
