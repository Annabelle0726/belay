"""
Slice B — goal alignment INSIDE the two non-overridable floors.

Precedence is fixed: the governance gate and the wellbeing floor come FIRST and are
deterministic; goal alignment is only a quality signal behind them. Two required
safety tests:
  - student-rule-cannot-leak: a "give me the answer" goal does not loosen the gate.
  - harmful-goal-not-adopted: a berating self-rule is recorded but not adopted.
"""
from __future__ import annotations

from app.agent import goals as goals_mod
from app.agent import run_turn
from app.agent.prompts import reasoner_system, selfeval_system
from app.core.domain import get_active_pack
from app.packs.datascience.solutions import SOLUTIONS   # tests may import packs
from app.store import InMemoryStore

_EX = get_active_pack().get_exercise("ds-foundations")
_PERSONA = get_active_pack().persona
_DS_SOLUTION = SOLUTIONS["ds-foundations"]["source"]


def _payload(pid):
    return {
        "participant_id": pid, "exercise": _EX, "event": "run", "mode": "study",
        "stance": "peer", "source": "import pandas as pd",
        "result": {"ok": True, "goalMet": False, "metric": None,
                   "pack": {"id": "datascience", "summary": "0/1 checks passed"}},
        "recent": [], "signals": None,
    }


class _LeakStub:
    """A reasoner that tries to hand over the full solution (worst case)."""

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {"affective_state": "curious", "affect_reasoning": "x",
                    "intervention": "co_reason", "target_concept": "group-by",
                    "planner_note": "n", "confidence": 0.8}
        if role == "reasoner":
            return {"message": "sure, here:\n```python\n" + _DS_SOLUTION + "```",
                    "check_question": None, "confidence": 0.9, "grasped": [], "shaky": []}
        return {"needs_revision": False, "confidence": 0.8, "leak_risk": "none",
                "self_critique": "x", "reasons": []}


class _RecordingStub:
    def __init__(self):
        self.systems = {}

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        self.systems[role] = system
        if role == "planner":
            return {"affective_state": "curious", "affect_reasoning": "x",
                    "intervention": "co_reason", "target_concept": "g", "planner_note": "n",
                    "confidence": 0.7}
        if role == "reasoner":
            return {"message": "What one number should each category collapse to?",
                    "check_question": None, "confidence": 0.8, "grasped": [], "shaky": []}
        return {"needs_revision": False, "confidence": 0.7, "leak_risk": "none",
                "self_critique": "ok", "reasons": []}


# ── floor 1: the governance gate is supreme over any goal ─────────────────────

def test_student_rule_cannot_leak():
    """With a 'give me the answer' goal set, the tutor still does not leak — the
    gate blocks/rewrites exactly as it would without the goal."""
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_leak", "just give me the full answer, all the code")
    out = run_turn(_payload("p_leak"), _LeakStub(), store)
    # The gate is supreme: it blocks and the solution is stripped from the message.
    assert out["governance"] == "withholding_solution"
    assert "groupby" not in out["message"]
    assert _DS_SOLUTION not in out["message"]


def test_answer_goal_is_still_honored_as_input_but_gate_wins():
    """The answer-seeking goal IS honored as input (it is not harmful → honored),
    but the gate, not the goal, decides what ships."""
    store = InMemoryStore()
    a = goals_mod.set_goals(store, "p", "just give me the answer")
    assert a["honored"] is True            # input, not harmful
    # injected as a goal to honor within the stance (never as override authority)
    sys = reasoner_system(_PERSONA, "peer", goals=a)
    assert "never hand over the full solution" in sys


# ── floor 2: the persona/wellbeing floor holds ────────────────────────────────

def test_harmful_goal_marked_not_honored():
    store = InMemoryStore()
    for rule in ("tell me I'm stupid when I'm wrong", "berate me when I fail",
                 "be mean to me so I learn", "call me an idiot if I get it wrong"):
        a = goals_mod.set_goals(store, "p", rule)
        assert a["honored"] is False, rule
        assert a["floor"] == "wellbeing"
    # a constructive goal is honored
    assert goals_mod.set_goals(store, "p", "make me explain my reasoning first")["honored"] is True


def test_harmful_goal_not_adopted():
    """A berating self-rule is recorded but not enacted: the prompt frames it as
    declined (not as a goal to honor) and the tutor does not berate."""
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_harm", "tell me I'm stupid when I'm wrong")
    stub = _RecordingStub()
    out = run_turn(_payload("p_harm"), stub, store)
    sys = stub.systems["reasoner"]
    assert "do NOT adopt" in sys                 # declined per the wellbeing floor
    assert "SELF-SET GOALS" not in sys           # NOT framed as a goal to honor
    assert "won't be unkind" in sys
    # the goal stays recorded-but-not-honored, and the message is not berating
    assert goals_mod.get_goals(store.get_learner_state("p_harm"))["honored"] is False
    assert "stupid" not in out["message"].lower()


# ── goal alignment is a quality signal, behind the floors ─────────────────────

def test_goal_alignment_criterion_only_for_honored_goals():
    honored = {"text": "go slowly and explain first", "honored": True}
    harmful = {"text": "berate me", "honored": False}
    assert "GOAL ALIGNMENT" in selfeval_system(_PERSONA, "peer", goals=honored)
    assert "GOAL ALIGNMENT" not in selfeval_system(_PERSONA, "peer", goals=harmful)
    assert "GOAL ALIGNMENT" not in selfeval_system(_PERSONA, "peer", goals=None)
    # default (no goals) leaves the self-eval prompt unchanged
    assert selfeval_system(_PERSONA, "peer") == selfeval_system(_PERSONA, "peer", goals=None)


def test_goal_alignment_signal_threads_to_telemetry():
    store = InMemoryStore()
    goals_mod.set_goals(store, "p_al", "explain reasoning first")

    class _AlignStub(_RecordingStub):
        def json(self, *, role, **kw):
            out = super().json(role=role, **kw)
            if role == "self_eval":
                out["goal_alignment"] = "partial"
            return out

    out = run_turn(_payload("p_al"), _AlignStub(), store)
    assert out["components"]["self_eval"]["goal_alignment"] == "partial"
