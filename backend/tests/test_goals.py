"""
Slice A — learner-authored goals: intake, pseudonymous storage, prompt injection.

Default behavior is unchanged when no goals are set (the injection is empty), so
existing families/tests stay green.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent import goals as goals_mod
from app.agent import run_turn
from app.agent.prompts import reasoner_system
from app.core.registry import get_active_pack
from app.integrations.quad import build_router
from app.store import ConsentRouter, InMemoryStore

_EX = get_active_pack().get_exercise("ds-foundations")
_PERSONA = get_active_pack().persona


def _payload(pid="p_goal", stance="peer"):
    return {
        "participant_id": pid,
        "exercise": _EX,
        "event": "run",
        "mode": "study",
        "stance": stance,
        "source": "import pandas as pd",
        "result": {
            "ok": True,
            "goalMet": False,
            "metric": None,
            "pack": {"id": "datascience", "summary": "0/1 checks passed"},
        },
        "recent": [],
        "signals": None,
    }


class _RecordingStub:
    """Captures the system prompt each component received; non-leaking outputs."""

    def __init__(self):
        self.systems = {}

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        self.systems[role] = system
        if role == "planner":
            return {
                "affective_state": "curious",
                "affect_reasoning": "x",
                "intervention": "co_reason",
                "target_concept": "group-by",
                "planner_note": "n",
                "confidence": 0.7,
            }
        if role == "reasoner":
            return {
                "message": "What one number should each category collapse to?",
                "check_question": None,
                "confidence": 0.8,
                "grasped": [],
                "shaky": [],
            }
        return {
            "needs_revision": False,
            "confidence": 0.7,
            "leak_risk": "none",
            "self_critique": "ok",
            "reasons": [],
        }


# ── storage: set / update / clear, pseudonymously ─────────────────────────────


def test_set_update_clear_goals():
    store = InMemoryStore()
    a = goals_mod.set_goals(store, "p1", "I want to explain my reasoning before coding")
    assert a["text"] == "I want to explain my reasoning before coding" and a["ts"]
    assert goals_mod.get_goals(store.get_learner_state("p1"))["text"].startswith(
        "I want to explain"
    )

    b = goals_mod.set_goals(store, "p1", "Now I want to focus on held-out evaluation")
    assert b["text"].startswith("Now I want to focus")  # updated
    assert b["ts"]

    goals_mod.clear_goals(store, "p1")
    assert goals_mod.get_goals(store.get_learner_state("p1")) is None


def test_goals_stored_per_learner_no_pii():
    store = InMemoryStore()
    goals_mod.set_goals(store, "gh:42", "go slowly")
    state = store.get_learner_state("gh:42")
    # The artifact is the student's words + a timestamp + the wellbeing-floor flag;
    # no identity fields, no PII.
    assert set(state["goals"]) <= {"text", "ts", "honored", "floor"}
    assert state["goals"]["honored"] is True
    assert store.get_learner_state("gh:99")["goals"] is None  # isolated per learner


def test_goals_survive_a_turn():
    """A normal turn must not clobber the student's goals."""
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_goal", "explain reasoning first")
    run_turn(_payload(), _RecordingStub(), store)
    assert (
        goals_mod.get_goals(store.get_learner_state("p_goal"))["text"] == "explain reasoning first"
    )


# ── injection: goals appear in the constructed prompt ─────────────────────────


def test_reasoner_system_injects_goals_within_stance():
    base = reasoner_system(_PERSONA, "peer")
    with_goals = reasoner_system(_PERSONA, "peer", goals={"text": "go slowly and explain first"})
    assert base == reasoner_system(_PERSONA, "peer", goals=None)  # default unchanged
    assert "go slowly and explain first" in with_goals
    assert "SELF-SET GOALS" in with_goals
    # framed as honored-within-stance, not as override authority
    assert "never hand over the full solution" in with_goals


def test_goal_appears_in_turn_reasoner_prompt():
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_goal", "I want to predict before I run")
    stub = _RecordingStub()
    run_turn(_payload(), stub, store)
    assert "I want to predict before I run" in stub.systems["reasoner"]


def test_no_goals_leaves_prompt_unchanged():
    store = InMemoryStore()
    stub = _RecordingStub()
    run_turn(_payload(), stub, store)  # no goals set
    assert "SELF-SET GOALS" not in stub.systems["reasoner"]


# ── HTTP + sidecar intake ─────────────────────────────────────────────────────


def _sidecar_client():
    app = FastAPI()
    app.include_router(
        build_router(ConsentRouter(InMemoryStore()), get_active_pack(), lambda: None)
    )
    return TestClient(app)


def test_sidecar_goals_route_sets_and_pii_checked():
    c = _sidecar_client()
    ok = c.post("/quad/v1/goals", json={"pseudo_id": "gh:7", "text": "go slowly"})
    assert ok.status_code == 200 and ok.json()["goals"]["text"] == "go slowly"
    # PII still rejected at the boundary (email in the goal text).
    bad = c.post("/quad/v1/goals", json={"pseudo_id": "gh:7", "text": "email me at a@b.edu"})
    assert bad.status_code == 422
    # capabilities advertises the goals route + opt-in learner_goals.
    caps = c.get("/quad/v1/capabilities").json()
    assert "POST /quad/v1/goals" in caps["routes"] and "learner_goals" in caps
