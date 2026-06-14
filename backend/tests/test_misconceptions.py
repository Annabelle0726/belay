"""
F6 misconception-tailored peer dialogue — offline tests.

Covers:
  1. for_exercise() structure: concept-specific + 3 cross-cutting items for each
     of the four studied exercises; safe fallback for an unknown id.
  2. all_inventory_seeds(): correct-answer stubs and distractors, with
     misconception_id on distractors.
  3. Context injection: peer and oracle paths carry misconceptions_context;
     control path does NOT (control short-circuits before the reasoner).
  4. misconception_id round-trips into the event payload from the reasoner.
  5. Governance: a peer_move-driven message still passes the withholding gate
     (governance, not the prompt, is the final safety guarantee).
"""
from __future__ import annotations

import json

import pytest

from app.agent import run_turn
from app.agent.context import build_context
from app.curriculum.misconceptions import (
    CROSS_CUTTING,
    all_inventory_seeds,
    for_exercise,
)
from app.curriculum import get_exercise
from app.store import InMemoryStore, make_event


# ── 1. for_exercise() ─────────────────────────────────────────────────────────

class TestForExercise:
    _CC_COUNT = len(CROSS_CUTTING["misconceptions"])  # 3 cross-cutting items

    def _check(self, ex_id: str, expected_concept_misconceptions: int) -> None:
        e = for_exercise(ex_id)
        assert e["expectations"], f"{ex_id}: expectations must be non-empty"
        assert len(e["misconceptions"]) == expected_concept_misconceptions + self._CC_COUNT, (
            f"{ex_id}: expected {expected_concept_misconceptions} concept + "
            f"{self._CC_COUNT} cross-cutting misconceptions"
        )
        for m in e["misconceptions"]:
            for key in ("id", "belief", "signature", "peer_move", "inventory_seed"):
                assert key in m, f"{ex_id}: missing key {key!r} on misconception"

    def test_superpose(self):
        self._check("superpose", 4)

    def test_bell(self):
        self._check("bell", 4)

    def test_uniform2(self):
        self._check("uniform2", 2)

    def test_ghz(self):
        self._check("ghz", 2)

    def test_unknown_id_safe_fallback(self):
        """for_exercise must never raise for an unknown id."""
        e = for_exercise("does_not_exist")
        assert e["concept"] == "(unknown exercise)"
        assert e["module"] == 0
        # Still gets cross-cutting expectations + misconceptions
        assert len(e["expectations"]) == len(CROSS_CUTTING["expectations"])
        assert len(e["misconceptions"]) == self._CC_COUNT

    def test_expectations_include_cross_cutting(self):
        """Cross-cutting expectations are merged for every known exercise."""
        for ex_id in ("superpose", "bell", "uniform2", "ghz"):
            e = for_exercise(ex_id)
            for cc_exp in CROSS_CUTTING["expectations"]:
                assert cc_exp in e["expectations"], (
                    f"{ex_id}: missing cross-cutting expectation"
                )


# ── 2. all_inventory_seeds() ─────────────────────────────────────────────────

class TestInventorySeeds:
    def test_both_kinds_present(self):
        seeds = all_inventory_seeds()
        kinds = {s["kind"] for s in seeds}
        assert "correct" in kinds
        assert "distractor" in kinds

    def test_distractors_have_misconception_id(self):
        for s in all_inventory_seeds():
            if s["kind"] == "distractor":
                assert "misconception_id" in s, "distractor missing misconception_id"
                assert s["misconception_id"], "distractor misconception_id must be non-empty"

    def test_correct_seeds_no_misconception_id(self):
        for s in all_inventory_seeds():
            if s["kind"] == "correct":
                assert "misconception_id" not in s

    def test_all_four_exercises_represented(self):
        ex_ids = {s["exercise"] for s in all_inventory_seeds()}
        for ex_id in ("superpose", "bell", "uniform2", "ghz"):
            assert ex_id in ex_ids

    def test_cross_cutting_seeds_present(self):
        ex_ids = {s["exercise"] for s in all_inventory_seeds()}
        assert "_cross_cutting" in ex_ids

    def test_sufficient_total_count(self):
        seeds = all_inventory_seeds()
        assert len(seeds) >= 20, "expected at least 20 inventory items across all entries"


# ── 3. Context injection ──────────────────────────────────────────────────────

def _make_payload(exercise_id: str, stance: str) -> dict:
    ex = get_exercise(exercise_id)
    return {
        "participant_id": "p_test",
        "exercise": ex,
        "event": "run",
        "mode": "study",
        "stance": stance,
        "source": "allocate 2\nsuperpose q0\nmeasure all",
        "result": None,
        "recent": [],
        "signals": None,
    }


class TestContextInjection:
    def test_peer_context_has_misconceptions(self):
        ctx = build_context(_make_payload("bell", "peer"),
                            {"grasped": [], "shaky": []}, 0)
        assert "misconceptions_context" in ctx
        mc = ctx["misconceptions_context"]
        assert mc["expectations"]
        assert len(mc["misconceptions"]) >= 1
        # Each misconception has signature + peer_move
        for m in mc["misconceptions"]:
            assert "signature" in m
            assert "peer_move" in m

    def test_oracle_context_has_misconceptions(self):
        ctx = build_context(_make_payload("bell", "oracle"),
                            {"grasped": [], "shaky": []}, 0)
        assert "misconceptions_context" in ctx, "oracle must also get misconception context"

    def test_control_context_has_no_misconceptions(self):
        ctx = build_context(_make_payload("bell", "control"),
                            {"grasped": [], "shaky": []}, 0)
        assert "misconceptions_context" not in ctx, (
            "control short-circuits before the reasoner; must not inject misconceptions"
        )

    def test_peer_context_has_signatures(self):
        """At least one misconception for 'bell' must carry a non-empty signature."""
        ctx = build_context(_make_payload("bell", "peer"),
                            {"grasped": [], "shaky": []}, 0)
        sigs = [m["signature"] for m in ctx["misconceptions_context"]["misconceptions"]]
        assert any(sigs), "expected at least one non-empty signature"

    def test_oracle_context_matches_peer_misconceptions(self):
        """Oracle and peer get the SAME misconception content — shared capability."""
        ctx_peer   = build_context(_make_payload("bell", "peer"),
                                   {"grasped": [], "shaky": []}, 0)
        ctx_oracle = build_context(_make_payload("bell", "oracle"),
                                   {"grasped": [], "shaky": []}, 0)
        assert (ctx_peer["misconceptions_context"]["misconceptions"]
                == ctx_oracle["misconceptions_context"]["misconceptions"])

    def test_all_four_exercises_have_context(self):
        for ex_id in ("superpose", "bell", "uniform2", "ghz"):
            ctx = build_context(_make_payload(ex_id, "peer"),
                                {"grasped": [], "shaky": []}, 0)
            assert ctx["misconceptions_context"]["misconceptions"]


# ── 4. misconception_id round-trip ───────────────────────────────────────────

class StubLLM:
    """Returns a matched misconception_id from the reasoner; planner/self_eval
    are standard stubs."""

    def __init__(self, misconception_id=None):
        self.misconception_id = misconception_id

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {"affective_state": "confusion",
                    "affect_reasoning": "signs of M1.1 confusion",
                    "intervention": "co_reason", "target_concept": "superposition",
                    "planner_note": "surface the misconception", "confidence": 0.7}
        if role == "reasoner":
            return {"message": "What would you expect if you ran the same program many times?",
                    "check_question": None, "confidence": 0.75,
                    "grasped": [], "shaky": ["superposition"],
                    "misconception_id": self.misconception_id}
        if role == "self_eval":
            return {"needs_revision": False, "confidence": 0.75, "leak_risk": "none",
                    "self_critique": "grounded and withholds the fix", "reasons": []}
        raise AssertionError(f"unexpected role: {role}")


def _run_payload(pid: str, stance: str) -> dict:
    return {
        "participant_id": pid,
        "exercise": get_exercise("superpose"),
        "event": "run", "mode": "study",
        "stance": stance,
        "source": "allocate 1\nsuperpose q0\nsuperpose q0\nmeasure all",
        "result": {"ok": True, "goalMet": False, "tvd": 0.5,
                   "dist": [{"bits": "0", "p": 1.0}]},
        "recent": [],
        "signals": {"attempts": 1, "distanceTrend": [0.5],
                    "repeatedError": False, "sinceLastProgress": 1},
    }


class TestMisconceptionIdTelemetry:
    def test_misconception_id_in_event_payload_peer(self):
        """When the stub returns M1.3-double-superpose, it must round-trip into
        the event payload under both telemetry.misconception_id and
        reasoner.misconception_id."""
        store = InMemoryStore()
        out = run_turn(_run_payload("p_mis", "peer"),
                       StubLLM(misconception_id="M1.3-double-superpose"), store)
        row = json.loads(store.export_jsonl("p_mis"))
        payload = row["payload"]
        assert payload["telemetry"]["misconception_id"] == "M1.3-double-superpose"
        assert payload["reasoner"]["misconception_id"] == "M1.3-double-superpose"

    def test_misconception_id_null_when_none(self):
        """When the stub returns no match, the field is null (not absent)."""
        store = InMemoryStore()
        run_turn(_run_payload("p_none", "peer"),
                 StubLLM(misconception_id=None), store)
        row = json.loads(store.export_jsonl("p_none"))
        payload = row["payload"]
        assert payload["telemetry"]["misconception_id"] is None
        assert payload["reasoner"]["misconception_id"] is None

    def test_misconception_id_null_on_control(self):
        """Control arm bypasses the reasoner; misconception_id is null by design."""
        store = InMemoryStore()
        out = run_turn(_run_payload("p_ctrl", "control"),
                       StubLLM(misconception_id="M1.1-classical-ignorance"), store)
        row = json.loads(store.export_jsonl("p_ctrl"))
        assert row["payload"]["telemetry"]["misconception_id"] is None

    def test_oracle_misconception_id_round_trips(self):
        """Oracle arm (full loop) also threads misconception_id through telemetry."""
        store = InMemoryStore()
        run_turn(_run_payload("p_orc", "oracle"),
                 StubLLM(misconception_id="M1.2-halfway-value"), store)
        row = json.loads(store.export_jsonl("p_orc"))
        assert row["payload"]["telemetry"]["misconception_id"] == "M1.2-halfway-value"


# ── 5. Governance: peer_move stays within withholding gate ────────────────────

class TestGovernanceStillGates:
    """A peer_move-driven message that would solve the exercise is still caught
    by governance.  The governance gate, not the prompt, is the guarantee."""

    def test_peer_move_message_passes_withholding_gate_when_no_code(self):
        """A Socratic peer_move with no solution code must NOT be blocked."""
        from app.agent import governance
        from app.curriculum import get_exercise

        ex = get_exercise("superpose")
        ctx = {"_exercise_full": ex, "recent_dialogue": []}
        plan = {"intervention": "co_reason"}
        # Typical peer_move: a question, no code
        draft = {
            "message": "What would you expect to see in the bars if you ran the "
                       "same program a hundred times — do you think the result would "
                       "be the same each time?",
            "confidence": 0.75,
        }
        gov = governance.check(ctx, plan, draft, {}, stance="peer")
        assert gov["block"] is False
        assert gov["flag"] == "none"

    def test_peer_move_with_leaking_code_is_still_blocked(self):
        """Even if the peer_move prompt drifts into giving the solution,
        governance still catches it deterministically.

        The snippet extraction picks up ≥2 consecutive op-matching lines and runs
        them through the grader; a goal-meeting snippet is blocked regardless of
        the surrounding pedagogical framing."""
        from app.agent import governance
        from app.curriculum import get_exercise

        ex = get_exercise("superpose")
        ctx = {"_exercise_full": ex, "recent_dialogue": []}
        plan = {"intervention": "co_reason"}
        # Three consecutive op lines → candidate snippet; grader returns goalMet=True
        draft = {
            "message": ("Try this and see what you get:\n"
                        "allocate 1\n"
                        "superpose q0\n"
                        "measure all\n"
                        "Does that match your expectation?"),
            "confidence": 0.75,
        }
        gov = governance.check(ctx, plan, draft, {}, stance="peer")
        assert gov["block"] is True
        assert gov["flag"] == "withholding_solution"
