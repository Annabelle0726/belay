"""
Deterministic tests for the persistent learner model (DS fixtures):
  - packs/datascience taxonomy: mappings + relevant_concepts (prereq edges)
  - agent/learner_model.py: update_concepts + due_review (via the active pack's taxonomy)
  - planner overlay: revisit fires in peer+calm, is coerced away in oracle/teach/
    goal_met/encourage/diagnose
"""
from __future__ import annotations

import pytest

from app.agent import learner_model as lm
from app.agent.planner import _rules_overlay
from app.packs.datascience.taxonomy import (
    CONCEPTS,
    EXERCISE_CONCEPT,
    MISCONCEPTION_CONCEPT,
    build_taxonomy,
)

TAX = build_taxonomy()

# ── helpers ───────────────────────────────────────────────────────────────────

_TS = "2026-06-03T00:00:00+00:00"


def _plan(**kw):
    base = {
        "affective_state": "curious",
        "affect_reasoning": "",
        "intervention": "co_reason",
        "target_concept": "linear-regression",
        "planner_note": "",
        "confidence": 0.8,
    }
    base.update(kw)
    return base


def _ctx(*, mode="study", goal_met=False, repeated_error=False, due_review=None):
    return {
        "mode": mode,
        "last_result": {"compiles": True, "goal_met": goal_met},
        "attempt_signals": {"repeatedError": repeated_error},
        "due_review": due_review or [],
    }


# ── §1 concept taxonomy ───────────────────────────────────────────────────────

class TestConceptMappings:
    def test_all_concept_ids_in_concepts_dict(self):
        for cid in EXERCISE_CONCEPT.values():
            assert cid in CONCEPTS, f"{cid} not in CONCEPTS"
        for cid in MISCONCEPTION_CONCEPT.values():
            assert cid in CONCEPTS, f"{cid} not in CONCEPTS"

    def test_concept_for_exercise_known(self):
        assert TAX.concept_for_exercise("ds-foundations") == "grouping-aggregation"
        assert TAX.concept_for_exercise("ds-regression") == "linear-regression"
        assert TAX.concept_for_exercise("ds-mlp") == "mlp"

    def test_concept_for_exercise_unknown_returns_none(self):
        assert TAX.concept_for_exercise("no_such_exercise") is None

    def test_concept_for_misconception_known(self):
        assert TAX.concept_for_misconception("DS-corr-causation") == "correlation-causation"
        assert TAX.concept_for_misconception("DS-train-test-leakage") == "data-leakage"
        assert TAX.concept_for_misconception("DS-learning-rate") == "learning-rate"

    def test_concept_for_misconception_unknown_returns_none(self):
        assert TAX.concept_for_misconception("DS-nonexistent") is None


class TestRelevantConcepts:
    def test_foundations_includes_concept_prereqs(self):
        rel = TAX.relevant_concepts("ds-foundations")
        assert "grouping-aggregation" in rel
        # Concept.prereqs of grouping-aggregation are consumed:
        assert "summary-statistics" in rel or "filtering" in rel

    def test_regression_includes_exercise_prereq_concept(self):
        rel = TAX.relevant_concepts("ds-regression")
        assert "linear-regression" in rel
        # exercise prereq ds-foundations' concept is pulled in:
        assert "grouping-aggregation" in rel

    def test_mlp_includes_prereqs(self):
        rel = TAX.relevant_concepts("ds-mlp")
        assert "mlp" in rel
        assert "linear-regression" in rel  # via exercise prereq ds-regression

    def test_unknown_exercise_returns_empty(self):
        assert len(TAX.relevant_concepts("no_such_exercise")) == 0


# ── §2 update_concepts (uses the active DS pack's taxonomy) ────────────────────

class TestUpdateConcepts:
    def test_touch_increments_evidence(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={}, misconception_id=None,
            repeated_error=False, now=_TS,
        )
        assert concepts["linear-regression"]["evidence"] == 1
        assert concepts["linear-regression"]["last_seen"] == _TS

    def test_solve_sets_grasped(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={"goal_met": True},
            misconception_id=None, repeated_error=False, now=_TS,
        )
        assert concepts["linear-regression"]["state"] == "grasped"

    def test_no_solve_stays_shaky(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={"goal_met": False},
            misconception_id=None, repeated_error=False, now=_TS,
        )
        assert concepts["linear-regression"]["state"] == "shaky"

    def test_misconception_sets_shaky(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={},
            misconception_id="DS-corr-causation", repeated_error=False, now=_TS,
        )
        assert concepts["correlation-causation"]["state"] == "shaky"

    def test_grasped_sticks_with_enough_evidence(self):
        prev = {"correlation-causation": {"state": "grasped", "evidence": 2,
                "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="ds-regression", result={},
            misconception_id="DS-corr-causation", repeated_error=False, now=_TS,
        )
        assert concepts["correlation-causation"]["state"] == "grasped"

    def test_grasped_overridden_with_low_evidence(self):
        prev = {"correlation-causation": {"state": "grasped", "evidence": 1,
                "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="ds-regression", result={},
            misconception_id="DS-corr-causation", repeated_error=False, now=_TS,
        )
        assert concepts["correlation-causation"]["state"] == "shaky"

    def test_repeated_error_sets_shaky(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={"goal_met": False},
            misconception_id=None, repeated_error=True, now=_TS,
        )
        assert concepts["linear-regression"]["state"] == "shaky"

    def test_repeated_error_does_not_override_firmly_grasped(self):
        prev = {"linear-regression": {"state": "grasped", "evidence": 2,
                "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="ds-regression", result={"goal_met": False},
            misconception_id=None, repeated_error=True, now=_TS,
        )
        assert concepts["linear-regression"]["state"] == "grasped"

    def test_revisit_updates_last_review(self):
        prev = {"grouping-aggregation": {"state": "shaky", "evidence": 1,
                "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        concepts = lm.update_concepts(
            prev, exercise_id="ds-regression", result={}, misconception_id=None,
            repeated_error=False, now=_TS, revisit_concept="grouping-aggregation",
        )
        assert concepts["grouping-aggregation"]["last_review"] == _TS
        assert concepts["grouping-aggregation"]["last_review_ex"] == "ds-regression"

    def test_revisit_unknown_concept_is_safe(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={}, misconception_id=None,
            repeated_error=False, now=_TS, revisit_concept="transformers",
        )
        assert "transformers" not in concepts

    def test_goalmet_in_camelcase_recognized(self):
        concepts = lm.update_concepts(
            {}, exercise_id="ds-regression", result={"goalMet": True},
            misconception_id=None, repeated_error=False, now=_TS,
        )
        assert concepts["linear-regression"]["state"] == "grasped"

    def test_does_not_mutate_prev(self):
        prev = {"linear-regression": {"state": "shaky", "evidence": 1,
                "last_seen": _TS, "last_review": None, "last_review_ex": None}}
        lm.update_concepts(
            prev, exercise_id="ds-regression", result={"goal_met": True},
            misconception_id=None, repeated_error=False, now=_TS,
        )
        assert prev["linear-regression"]["state"] == "shaky"


# ── §3 due_review ─────────────────────────────────────────────────────────────

class TestDueReview:
    def _entry(self, state, last_review_ex=None):
        return {"state": state, "evidence": 1, "last_seen": _TS,
                "last_review": None, "last_review_ex": last_review_ex}

    def test_shaky_relevant_not_reviewed_is_due(self):
        # grouping-aggregation is relevant to ds-regression (via the exercise prereq).
        concepts = {"grouping-aggregation": self._entry("shaky")}
        due = lm.due_review(concepts, "ds-regression")
        assert "grouping-aggregation" in due

    def test_grasped_is_not_due(self):
        concepts = {"grouping-aggregation": self._entry("grasped")}
        assert "grouping-aggregation" not in lm.due_review(concepts, "ds-regression")

    def test_irrelevant_concept_not_due(self):
        concepts = {"transformers": self._entry("shaky")}
        assert "transformers" not in lm.due_review(concepts, "ds-regression")

    def test_already_reviewed_on_this_exercise_not_due(self):
        concepts = {"linear-regression": self._entry("shaky", last_review_ex="ds-regression")}
        assert "linear-regression" not in lm.due_review(concepts, "ds-regression")

    def test_reviewed_on_different_exercise_is_still_due(self):
        concepts = {"linear-regression": self._entry("shaky", last_review_ex="ds-mlp")}
        assert "linear-regression" in lm.due_review(concepts, "ds-regression")

    def test_empty_concepts_returns_empty(self):
        assert lm.due_review({}, "ds-regression") == []

    def test_own_concept_shaky_is_due_for_self(self):
        concepts = {"linear-regression": self._entry("shaky")}
        assert "linear-regression" in lm.due_review(concepts, "ds-regression")


# ── §4 planner overlay ────────────────────────────────────────────────────────

class TestPlannerOverlay:
    def test_calm_turn_with_due_review_becomes_revisit(self):
        ctx = _ctx(due_review=[{"id": "grouping-aggregation", "label": "Group-by and aggregation"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "revisit"
        assert result["revisit_concept"] == "grouping-aggregation"

    def test_observe_turn_with_due_review_becomes_revisit(self):
        ctx = _ctx(due_review=[{"id": "linear-regression", "label": "Linear regression"}])
        result = _rules_overlay(_plan(intervention="observe"), ctx, stance="peer")
        assert result["intervention"] == "revisit"

    def test_no_due_review_stays_co_reason(self):
        ctx = _ctx(due_review=[])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "co_reason"

    def test_revisit_not_in_oracle(self):
        ctx = _ctx(due_review=[{"id": "grouping-aggregation", "label": "x"}])
        result = _rules_overlay(_plan(intervention="revisit"), ctx, stance="oracle")
        assert result["intervention"] in ("diagnose", "co_reason", "observe")
        assert result["intervention"] != "revisit"

    def test_teach_mode_outranks_revisit(self):
        ctx = _ctx(mode="teach", due_review=[{"id": "grouping-aggregation", "label": "x"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "reciprocate"

    def test_goal_met_outranks_revisit(self):
        ctx = _ctx(goal_met=True, due_review=[{"id": "grouping-aggregation", "label": "x"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "stretch"

    def test_encourage_outranks_revisit(self):
        ctx = _ctx(due_review=[{"id": "grouping-aggregation", "label": "x"}])
        plan = _plan(intervention="co_reason", affective_state="frustration")
        result = _rules_overlay(plan, ctx, stance="peer")
        assert result["intervention"] == "encourage"

    def test_repeated_error_outranks_revisit(self):
        ctx = _ctx(repeated_error=True, due_review=[{"id": "grouping-aggregation", "label": "x"}])
        result = _rules_overlay(_plan(intervention="co_reason"), ctx, stance="peer")
        assert result["intervention"] == "diagnose"

    def test_diagnose_not_overridden_by_revisit(self):
        ctx = _ctx(due_review=[{"id": "grouping-aggregation", "label": "x"}])
        result = _rules_overlay(_plan(intervention="diagnose"), ctx, stance="peer")
        assert result["intervention"] == "diagnose"
