"""
F6 misconception-tailored peer dialogue — offline tests (DS fixtures).

Covers:
  1. for_exercise() structure: concept-specific + cross-cutting items per exercise;
     safe fallback for an unknown id.
  2. all_inventory_seeds(): correct-answer stubs and distractors.
  3. Context injection: peer and oracle carry misconceptions_context; control does not.
  4. misconception_id round-trips into the event payload from the reasoner.
  5. Governance: a peer_move message still passes the gate; a leaking one is blocked.
"""
from __future__ import annotations

import json

from app.agent import run_turn
from app.agent.context import build_context
from app.core.domain import get_active_pack
from app.packs.datascience.misconceptions import (
    CROSS_CUTTING,
    all_inventory_seeds,
    for_exercise,
)
from app.packs.datascience.solutions import SOLUTIONS
from app.store import InMemoryStore

_PACK = get_active_pack()


# ── 1. for_exercise() ─────────────────────────────────────────────────────────

class TestForExercise:
    _CC = len(CROSS_CUTTING["misconceptions"])  # 7 cross-cutting items

    def _check(self, ex_id: str, own: int) -> None:
        e = for_exercise(ex_id)
        assert e["expectations"], f"{ex_id}: expectations must be non-empty"
        assert len(e["misconceptions"]) == own + self._CC
        for m in e["misconceptions"]:
            for key in ("id", "belief", "signature", "peer_move"):
                assert key in m, f"{ex_id}: missing key {key!r}"

    def test_foundations(self):
        self._check("ds-foundations", 4)

    def test_regression(self):
        self._check("ds-regression", 4)

    def test_mlp(self):
        self._check("ds-mlp", 3)

    def test_unknown_id_safe_fallback(self):
        e = for_exercise("no_such_exercise")
        assert len(e["misconceptions"]) == self._CC   # cross-cutting only
        assert e["expectations"]


# ── 2. all_inventory_seeds() ──────────────────────────────────────────────────

class TestInventorySeeds:
    def test_correct_items_have_no_misconception_id(self):
        for s in all_inventory_seeds():
            if s["kind"] == "correct":
                assert "misconception_id" not in s

    def test_distractors_have_misconception_id(self):
        for s in all_inventory_seeds():
            if s["kind"] == "distractor":
                assert s.get("misconception_id")

    def test_all_exercises_represented(self):
        ex_ids = {s["exercise"] for s in all_inventory_seeds()}
        for ex_id in ("ds-foundations", "ds-regression", "ds-mlp", "_cross_cutting"):
            assert ex_id in ex_ids

    def test_sufficient_total_count(self):
        assert len(all_inventory_seeds()) >= 20


# ── 3. Context injection ──────────────────────────────────────────────────────

def _make_payload(exercise_id: str, stance: str) -> dict:
    return {
        "participant_id": "p_test",
        "exercise": _PACK.get_exercise(exercise_id),
        "event": "run", "mode": "study", "stance": stance,
        "source": "import pandas as pd", "result": None,
        "recent": [], "signals": None,
    }


class TestContextInjection:
    def test_peer_context_has_misconceptions(self):
        ctx = build_context(_make_payload("ds-foundations", "peer"),
                            {"grasped": [], "shaky": []}, 0)
        assert "misconceptions_context" in ctx
        mc = ctx["misconceptions_context"]
        assert mc["expectations"] and len(mc["misconceptions"]) >= 1
        for m in mc["misconceptions"]:
            assert "signature" in m and "peer_move" in m

    def test_oracle_context_has_misconceptions(self):
        ctx = build_context(_make_payload("ds-regression", "oracle"),
                            {"grasped": [], "shaky": []}, 0)
        assert "misconceptions_context" in ctx

    def test_control_context_has_no_misconceptions(self):
        ctx = build_context(_make_payload("ds-foundations", "control"),
                            {"grasped": [], "shaky": []}, 0)
        assert "misconceptions_context" not in ctx

    def test_oracle_matches_peer_misconceptions(self):
        peer = build_context(_make_payload("ds-foundations", "peer"),
                             {"grasped": [], "shaky": []}, 0)
        oracle = build_context(_make_payload("ds-foundations", "oracle"),
                               {"grasped": [], "shaky": []}, 0)
        assert (peer["misconceptions_context"]["misconceptions"]
                == oracle["misconceptions_context"]["misconceptions"])

    def test_all_exercises_have_context(self):
        for ex_id in ("ds-foundations", "ds-regression", "ds-mlp"):
            ctx = build_context(_make_payload(ex_id, "peer"),
                                {"grasped": [], "shaky": []}, 0)
            assert ctx["misconceptions_context"]["misconceptions"]


# ── 4. misconception_id round-trip ───────────────────────────────────────────

class StubLLM:
    def __init__(self, misconception_id=None):
        self.misconception_id = misconception_id

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {"affective_state": "confusion", "affect_reasoning": "signs of confusion",
                    "intervention": "co_reason", "target_concept": "linear-regression",
                    "planner_note": "surface the misconception", "confidence": 0.7}
        if role == "reasoner":
            return {"message": "What would change if you held out the test split first?",
                    "check_question": None, "confidence": 0.75,
                    "grasped": [], "shaky": ["generalization"],
                    "misconception_id": self.misconception_id}
        if role == "self_eval":
            return {"needs_revision": False, "confidence": 0.75, "leak_risk": "none",
                    "self_critique": "grounded and withholds the fix", "reasons": []}
        raise AssertionError(f"unexpected role: {role}")


def _run_payload(pid: str, stance: str) -> dict:
    return {
        "participant_id": pid, "exercise": _PACK.get_exercise("ds-regression"),
        "event": "run", "mode": "study", "stance": stance,
        "source": "import numpy as np",
        "result": {"ok": True, "goalMet": False, "metric": 0.2,
                   "pack": {"id": "datascience", "summary": "0/1 checks passed"}},
        "recent": [], "signals": {"attempts": 1, "repeatedError": False, "sinceLastProgress": 1},
    }


class TestMisconceptionIdTelemetry:
    def test_round_trips_peer(self):
        store = InMemoryStore()
        run_turn(_run_payload("p_mis", "peer"),
                 StubLLM(misconception_id="DS-corr-causation"), store)
        payload = json.loads(store.export_jsonl("p_mis"))["payload"]
        assert payload["telemetry"]["misconception_id"] == "DS-corr-causation"
        assert payload["reasoner"]["misconception_id"] == "DS-corr-causation"

    def test_null_when_none(self):
        store = InMemoryStore()
        run_turn(_run_payload("p_none", "peer"), StubLLM(misconception_id=None), store)
        payload = json.loads(store.export_jsonl("p_none"))["payload"]
        assert payload["telemetry"]["misconception_id"] is None

    def test_null_on_control(self):
        store = InMemoryStore()
        run_turn(_run_payload("p_ctrl", "control"),
                 StubLLM(misconception_id="DS-corr-causation"), store)
        assert json.loads(store.export_jsonl("p_ctrl"))["payload"]["telemetry"]["misconception_id"] is None


# ── 5. Governance still gates ─────────────────────────────────────────────────

class TestGovernanceStillGates:
    def test_socratic_peer_move_passes_gate(self):
        from app.agent import governance
        ex = _PACK.get_exercise("ds-foundations")
        ctx = {"_exercise_full": ex, "recent_dialogue": []}
        draft = {"message": "What one number should each category collapse to?", "confidence": 0.75}
        gov = governance.check(ctx, {"intervention": "co_reason"}, draft, {}, stance="peer")
        assert gov["block"] is False
        assert gov["flag"] == "none"

    def test_leaking_code_is_still_blocked(self):
        from app.agent import governance
        ex = _PACK.get_exercise("ds-foundations")
        ctx = {"_exercise_full": ex, "recent_dialogue": []}
        draft = {"message": "Try this:\n```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```",
                 "confidence": 0.75}
        gov = governance.check(ctx, {"intervention": "co_reason"}, draft, {}, stance="peer")
        assert gov["block"] is True
        assert gov["flag"] == "withholding_solution"
