"""
Slice C — the reflect intervention, reflection storage, and additive §6 events.

reflect is selectable both ways (tutor-offered by the planner; student-initiated by
request/cue); reflections are stored pseudonymously and linked to the goal in force;
and the four additive event types appear with the stable 8-field row shape.
"""

from __future__ import annotations

import json

from app.agent import goals as goals_mod
from app.agent import run_turn
from app.core.registry import get_active_pack
from app.store import InMemoryStore

_EX = get_active_pack().get_exercise("ds-foundations")
_ROW_FIELDS = {
    "participant_id",
    "ts",
    "exercise_id",
    "mode",
    "event_type",
    "stance",
    "payload",
    "note",
}


def _payload(pid="p_ref", recent=None, request=None):
    return {
        "participant_id": pid,
        "exercise": _EX,
        "event": "chat",
        "mode": "study",
        "stance": "peer",
        "source": "import pandas as pd",
        "result": {
            "ok": True,
            "goalMet": False,
            "metric": None,
            "pack": {"id": "datascience", "summary": "0/1 checks passed"},
        },
        "recent": recent or [],
        "signals": None,
        "request": request,
    }


class _Stub:
    """Configurable: the planner returns `intervention`; the reasoner is non-leaking."""

    def __init__(self, intervention="co_reason"):
        self.intervention = intervention

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {
                "affective_state": "curious",
                "affect_reasoning": "x",
                "intervention": self.intervention,
                "target_concept": "group-by",
                "planner_note": "n",
                "confidence": 0.7,
            }
        if role == "reasoner":
            return {
                "message": "you wanted to explain your reasoning first — how's that going here?",
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


# ── reflect is selectable both ways ───────────────────────────────────────────


def test_reflect_is_tutor_offered_by_planner():
    """The planner can select reflect; it survives the overlay (a valid intervention)."""
    out = run_turn(_payload(), _Stub(intervention="reflect"), InMemoryStore())
    assert out["intervention"] == "reflect"


def test_reflect_is_student_initiated_by_request():
    """An explicit request:'reflect' forces the reflect intervention regardless of
    the planner's pick."""
    out = run_turn(_payload(request="reflect"), _Stub(intervention="co_reason"), InMemoryStore())
    assert out["intervention"] == "reflect"


def test_reflect_is_student_initiated_by_dialogue_cue():
    recent = [{"who": "student", "text": "can we reflect on my goal for a sec?"}]
    out = run_turn(_payload(recent=recent), _Stub(intervention="co_reason"), InMemoryStore())
    assert out["intervention"] == "reflect"


def test_no_reflect_by_default():
    out = run_turn(_payload(), _Stub(intervention="co_reason"), InMemoryStore())
    assert out["intervention"] != "reflect"


# ── reflection storage, linked to the goal ────────────────────────────────────


def test_reflection_stored_and_linked_to_goal():
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_r", "explain my reasoning before I code")
    refl = goals_mod.add_reflection(store, "p_r", "I jumped to code again without explaining")
    assert refl["text"].startswith("I jumped to code")
    assert refl["goal_text"] == "explain my reasoning before I code"  # linked
    assert refl["ts"]
    stored = goals_mod.get_reflections(store.get_learner_state("p_r"))
    assert len(stored) == 1 and stored[0]["goal_text"] == "explain my reasoning before I code"


def test_reflection_without_goal_links_to_none():
    store = InMemoryStore()
    refl = goals_mod.add_reflection(store, "p_n", "I think I'm guessing too much")
    assert refl["goal_text"] is None


# ── additive §6 events (additive only; stable 8-field row shape) ──────────────


def _event_types(store, pid):
    rows = [json.loads(line) for line in store.export_jsonl(pid).splitlines() if line]
    for r in rows:
        assert set(r) == _ROW_FIELDS, f"row shape drifted: {set(r)}"
    return [r["event_type"] for r in rows]


def test_all_four_additive_events_present():
    store = InMemoryStore()
    # goal_set
    goals_mod.set_goals(store, "p_ev", "explain reasoning first")
    # goal_alignment_check (honored goal) + reflect (reflect turn)
    run_turn(_payload(pid="p_ev", request="reflect"), _Stub(), store)
    # reflection_recorded
    goals_mod.add_reflection(store, "p_ev", "still jumping to code")

    types = _event_types(store, "p_ev")
    for et in ("goal_set", "goal_alignment_check", "reflect", "reflection_recorded", "turn"):
        assert et in types, f"missing additive event {et!r}; got {types}"


def test_no_extra_events_without_goals():
    """Default behavior unchanged: a plain turn emits only the turn event."""
    store = InMemoryStore()
    run_turn(_payload(pid="p_plain"), _Stub(intervention="co_reason"), store)
    assert _event_types(store, "p_plain") == ["turn"]


def test_goal_set_event_records_honored_flag():
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_h", "tell me I'm stupid when I'm wrong")  # harmful
    rows = [json.loads(l) for l in store.export_jsonl("p_h").splitlines() if l]
    gs = [r for r in rows if r["event_type"] == "goal_set"][0]
    assert gs["payload"]["honored"] is False
