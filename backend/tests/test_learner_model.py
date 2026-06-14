"""
Deterministic tests for the persistent learner model:
  - curriculum/concepts.py: taxonomy mappings + relevant_concepts
  - agent/learner_model.py: update_concepts + due_review
  - planner overlay: revisit fires in peer+calm, is coerced away in oracle/teach/
    goal_met/encourage/diagnose
"""
from __future__ import annotations

import pytest

from app.curriculum.concepts import (
    CONCEPTS,
    EXERCISE_CONCEPT,
    MISCONCEPTION_CONCEPT,
    concept_for_exercise,
    concept_for_misconception,
    relevant_concepts,
)
from app.agent import learner_model as lm
from app.agent.planner import _rules_overlay


# ── helpers ───────────────────────────────────────────────────────────────────

_TS = "2026-06-03T00:00:00+00:00"


def _plan(**kw):
    base = {
        "affective_state": "curious",
        "affect_reasoning": "",
        "intervention": "co_reason",
        "target_concept": "entanglement",
        "planner_note": "",
        "confidence": 0.8,
    }
    base.update(kw)
    return base


def _ctx(*, mode="study", goal_met=False, repeated_error=False, due_review=None):
    return {
        "mode": mode,
        "last_result": {"compiles": True, "goal_met": goal_met, "goal_met": goal_met},
        "attempt_signals": {"repeatedError": repeated_error},
        "due_review": due_review or [],
    }


# ── §1 concept taxonomy ───────────────────────────────────────────────────────

class TestConceptMappings:
    def test_all_concept_ids_in_concepts_dict(self):
        """Every id in EXERCISE_CONCEPT and MISCONCEPTION_CONCEPT must be a key in CONCEPTS."""
        for cid in EXERCISE_CONCEPT.values():
            assert cid in CONCEPTS, f"{cid} not in CONCEPTS"
        for cid in MISCONCEPTION_CONCEPT.values():
            assert cid in CONCEPTS, f"{cid} not in CONCEPTS"

    def test_concept_for_exercise_known(self):
        assert concept_for_exercise("bell") == "entanglement"
        assert concept_for_exercise("superpose") == "superposition"
        assert concept_for_exercise("flip") == "determinism"
        assert concept_for_exercise("uniform2") == "independence"
        assert concept_for_exercise("ghz") == "scaling"
        assert concept_for_exercise("phasekick") == "phase"

    def test_concept_for_exercise_unknown_returns_none(self):
        assert concept_for_exercise("no_such_exercise") is None

    def test_concept_for_misconception_known(self):
        assert concept_for_misconception("M1.1-classical-ignorance") == "superposition"
        assert concept_for_misconception("M1.4-measurement-cosmetic") == "measurement"
        assert concept_for_misconception("M2.1-superpose-both-is-entangle") == "entanglement"
        assert concept_for_misconception("M2.5-uniform-needs-entangle") == "independence"
        assert concept_for_misconception("M2.7-ghz-superpose-all") == "scaling"
        assert concept_for_misconception("M3.1-literal-gates") == "abstraction"

    def test_concept_for_misconception_unknown_returns_none(self):
        assert concept_for_misconception("M99.0-nonexistent") is None


class TestRelevantConcepts:
    def test_superpose_own_only(self):
        rel = relevant_concepts("superpose")
        assert rel == frozenset({"superposition"})

    def test_flip_includes_prereq_superposition(self):
        rel = relevant_concepts("flip")
        assert "determinism" in rel
        assert "superposition" in rel

    def test_bell_includes_prereq(self):
        rel = relevant_concepts("bell")
        assert "entanglement" in rel
        assert "superposition" in rel

    def test_uniform2_includes_bell_prereq(self):
        rel = relevant_concepts("uniform2")
        assert "independence" in rel
        assert "entanglement" in rel

    def test_ghz_includes_bell_prereq(self):
        rel = relevant_concepts("ghz")
        assert "scaling" in rel
        assert "entanglement" in rel

    def test_phasekick_includes_two_prereqs(self):
        rel = relevant_concepts("phasekick")
        assert "phase" in rel
        assert "entanglement" in rel
        assert "superposition" in rel

    def test_unknown_exercise_returns_empty(self):
        rel = relevant_concepts("no_such_exercise")
        assert len(rel) == 0


# ── §2 update_concepts ────────────────────────────────────────────────────────

class TestUpdateConcepts:
    def test_touch_increments_evidence(self):
        concepts = lm.update_concepts(
            {}, exercise_id="bell", result={}, misconception_id=None,
            repeated_error=False, now=_TS,
        )
        assert concepts["entanglement"]["evidence"] == 1
        assert concepts["entanglement"]["last_seen"] == _TS

    def test_solve_sets_grasped(self):
        concepts = lm.update_concepts(
            {}, exercise_id="bell",
            result={"goal_met": True}, misconception_id=None,
            repeated_error=False, now=_TS,
        )
        assert concepts["entanglement"]["state"] == "grasped"

    def test_no_solve_stays_shaky(self):
        concepts = lm.update_concepts(
            {}, exercise_id="bell",
            result={"goal_met": False}, misconception_id=None,
            repeated_error=False, now=_TS,
        )
        assert concepts["entanglement"]["state"] == "shaky"

    def test_misconception_sets_shaky(self):
        concepts = lm.update_concepts(
            {}, exercise_id="bell",
            result={}, misconception_id="M1.1-classical-ignorance",
            repeated_error=False, now=_TS,
        )
        assert concepts["superposition"]["state"] == "shaky"

    def test_grasped_sticks_with_enough_evidence(self):
        """A grasped concept with evidence≥2 must not be downgraded by a misconception."""
        prev = {"superposition": {"state": "grasped", "evidence": 2,
                                   "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="bell",
            result={}, misconception_id="M1.1-classical-ignorance",
            repeated_error=False, now=_TS,
        )
        assert concepts["superposition"]["state"] == "grasped"

    def test_grasped_overridden_with_low_evidence(self):
        """Grasped with evidence=1 is NOT firmly grasped — misconception can override it."""
        prev = {"superposition": {"state": "grasped", "evidence": 1,
                                   "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="bell",
            result={}, misconception_id="M1.1-classical-ignorance",
            repeated_error=False, now=_TS,
        )
        assert concepts["superposition"]["state"] == "shaky"

    def test_repeated_error_sets_shaky(self):
        concepts = lm.update_concepts(
            {}, exercise_id="bell",
            result={"goal_met": False}, misconception_id=None,
            repeated_error=True, now=_TS,
        )
        assert concepts["entanglement"]["state"] == "shaky"

    def test_repeated_error_does_not_override_firmly_grasped(self):
        prev = {"entanglement": {"state": "grasped", "evidence": 2,
                                  "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="bell",
            result={"goal_met": False}, misconception_id=None,
            repeated_error=True, now=_TS,
        )
        assert concepts["entanglement"]["state"] == "grasped"

    def test_revisit_updates_last_review(self):
        prev = {"superposition": {"state": "shaky", "evidence": 1,
                                   "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="bell",
            result={}, misconception_id=None,
            repeated_error=False, now=_TS,
            revisit_concept="superposition",
        )
        assert concepts["superposition"]["last_review"] == _TS
        assert concepts["superposition"]["last_review_ex"] == "bell"

    def test_revisit_unknown_concept_is_safe(self):
        """revisit_concept not in concepts should not raise."""
        concepts = lm.update_concepts(
            {}, exercise_id="bell",
            result={}, misconception_id=None,
            repeated_error=False, now=_TS,
            revisit_concept="phase",  # not in prev
        )
        assert "phase" not in concepts  # not created by revisit alone

    def test_goalmet_in_camelcase_recognized(self):
        """Older traces may use goalMet (camelCase)."""
        concepts = lm.update_concepts(
            {}, exercise_id="bell",
            result={"goalMet": True}, misconception_id=None,
            repeated_error=False, now=_TS,
        )
        assert concepts["entanglement"]["state"] == "grasped"

    def test_does_not_mutate_prev(self):
        """update_concepts must return a new dict; prev is unchanged."""
        prev = {"entanglement": {"state": "shaky", "evidence": 1,
                                  "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        lm.update_concepts(
            prev, exercise_id="bell",
            result={"goal_met": True}, misconception_id=None,
            repeated_error=False, now=_TS,
        )
        assert prev["entanglement"]["state"] == "shaky"


# ── §3 due_review ─────────────────────────────────────────────────────────────

class TestDueReview:
    def _entry(self, state, last_review_ex=None):
        return {"state": state, "evidence": 1, "last_seen": _TS,
                "last_review": None, "last_review_ex": last_review_ex}

    def test_shaky_relevant_not_reviewed_is_due(self):
        concepts = {"superposition": self._entry("shaky")}
        due = lm.due_review(concepts, "bell")  # bell prereq is superposition
        assert "superposition" in due

    def test_grasped_is_not_due(self):
        concepts = {"superposition": self._entry("grasped")}
        due = lm.due_review(concepts, "bell")
        assert "superposition" not in due

    def test_irrelevant_concept_not_due(self):
        """phase is not in bell's relevant_concepts."""
        concepts = {"phase": self._entry("shaky")}
        due = lm.due_review(concepts, "bell")
        assert "phase" not in due

    def test_already_reviewed_on_this_exercise_not_due(self):
        concepts = {"superposition": self._entry("shaky", last_review_ex="bell")}
        due = lm.due_review(concepts, "bell")
        assert "superposition" not in due

    def test_reviewed_on_different_exercise_is_still_due(self):
        concepts = {"superposition": self._entry("shaky", last_review_ex="uniform2")}
        due = lm.due_review(concepts, "bell")
        assert "superposition" in due

    def test_empty_concepts_returns_empty(self):
        assert lm.due_review({}, "bell") == []

    def test_own_concept_shaky_is_due_for_self(self):
        """entanglement shaky → due for bell (bell's own concept)."""
        concepts = {"entanglement": self._entry("shaky")}
        due = lm.due_review(concepts, "bell")
        assert "entanglement" in due


# ── §4 planner overlay ────────────────────────────────────────────────────────

class TestPlannerOverlay:
    def test_calm_turn_with_due_review_becomes_revisit(self):
        ctx = _ctx(due_review=[{"id": "superposition", "label": "Single-qubit superposition"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "revisit"
        assert result["revisit_concept"] == "superposition"

    def test_observe_turn_with_due_review_becomes_revisit(self):
        ctx = _ctx(due_review=[{"id": "entanglement", "label": "Entanglement"}])
        result = _rules_overlay(_plan(intervention="observe"), ctx, stance="peer")
        assert result["intervention"] == "revisit"

    def test_no_due_review_stays_co_reason(self):
        ctx = _ctx(due_review=[])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "co_reason"

    def test_revisit_not_in_oracle(self):
        """Oracle coerces revisit → diagnose."""
        ctx = _ctx(due_review=[{"id": "superposition", "label": "x"}])
        plan = _plan(intervention="revisit")
        result = _rules_overlay(plan, ctx, stance="oracle")
        assert result["intervention"] in ("diagnose", "co_reason", "observe")
        assert result["intervention"] != "revisit"

    def test_teach_mode_outranks_revisit(self):
        ctx = _ctx(mode="teach", due_review=[{"id": "superposition", "label": "x"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "reciprocate"

    def test_goal_met_outranks_revisit(self):
        ctx = _ctx(goal_met=True, due_review=[{"id": "superposition", "label": "x"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "stretch"

    def test_encourage_outranks_revisit(self):
        """frustration affect fires before revisit check."""
        ctx = _ctx(due_review=[{"id": "superposition", "label": "x"}])
        plan = _plan(intervention="co_reason", affective_state="frustration")
        result = _rules_overlay(plan, ctx, stance="peer")
        assert result["intervention"] == "encourage"

    def test_repeated_error_outranks_revisit(self):
        ctx = _ctx(repeated_error=True, due_review=[{"id": "superposition", "label": "x"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "diagnose"

    def test_diagnose_not_overridden_by_revisit(self):
        """If the model chose diagnose and there's a due_review, diagnose wins."""
        ctx = _ctx(due_review=[{"id": "superposition", "label": "x"}])
        result = _rules_overlay(_plan(intervention="diagnose"), ctx, stance="peer")
        assert result["intervention"] == "diagnose"
