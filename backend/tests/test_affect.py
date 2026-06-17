"""
Affect-adaptive planner overlay tests — deterministic, no LLM.

Calls _rules_overlay directly with synthetic plan/ctx dicts to verify the
precedence order:
  1. teach mode  → reciprocate  (returns immediately)
  2. goal_met    → stretch
  3. peer affect → encourage / observe  (gated stance != oracle)
  4. repeatedError → diagnose  (fires only when affect didn't claim the turn)
  5. oracle coercion  (encourage → diagnose)
"""
from __future__ import annotations

from app.agent.planner import (
    _ORACLE_INTERVENTIONS,
    _VALID_INTERVENTIONS,
    NEEDS_SUPPORT,
    _rules_overlay,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _ctx(mode="study", goal_met=False, repeated_error=False):
    return {
        "mode": mode,
        "last_result": {"goal_met": goal_met} if goal_met else "no run yet",
        "attempt_signals": {
            "repeatedError": repeated_error,
            "sinceLastProgress": 0, "distanceTrend": [], "attempts": 1,
        },
        "exercise": {"concept": "entanglement"},
    }


def _plan(affect="curious", intervention="co_reason"):
    return {
        "affective_state": affect,
        "intervention": intervention,
        "planner_note": "",
        "target_concept": "entanglement",
        "confidence": 0.7,
    }


# ── 1. Set membership ─────────────────────────────────────────────────────────

def test_encourage_in_valid_interventions():
    assert "encourage" in _VALID_INTERVENTIONS


def test_encourage_not_in_oracle_interventions():
    assert "encourage" not in _ORACLE_INTERVENTIONS


def test_needs_support_contents():
    assert NEEDS_SUPPORT == {"frustration", "disengaged"}


# ── 2. peer + frustration → encourage ────────────────────────────────────────

def test_peer_frustration_yields_encourage():
    p = _plan(affect="frustration", intervention="co_reason")
    out = _rules_overlay(p, _ctx(), stance="peer")
    assert out["intervention"] == "encourage"
    assert "frustration" in out["planner_note"]


# ── 3. peer + disengaged → encourage ─────────────────────────────────────────

def test_peer_disengaged_yields_encourage():
    p = _plan(affect="disengaged", intervention="observe")
    out = _rules_overlay(p, _ctx(), stance="peer")
    assert out["intervention"] == "encourage"
    assert "disengaged" in out["planner_note"]


# ── 4. peer + flow + diagnose → observe ──────────────────────────────────────

def test_peer_flow_diagnose_yields_observe():
    p = _plan(affect="flow", intervention="diagnose")
    out = _rules_overlay(p, _ctx(), stance="peer")
    assert out["intervention"] == "observe"
    assert "flow" in out["planner_note"]


def test_peer_flow_worked_analogy_yields_observe():
    p = _plan(affect="flow", intervention="worked_analogy")
    out = _rules_overlay(p, _ctx(), stance="peer")
    assert out["intervention"] == "observe"


# ── 5. goal_met precedence beats frustration ─────────────────────────────────

def test_peer_frustration_goal_met_yields_stretch():
    p = _plan(affect="frustration", intervention="co_reason")
    out = _rules_overlay(p, _ctx(goal_met=True), stance="peer")
    assert out["intervention"] == "stretch"


# ── 6. teach mode precedence beats frustration ───────────────────────────────

def test_teach_frustration_yields_reciprocate():
    p = _plan(affect="frustration", intervention="co_reason")
    out = _rules_overlay(p, _ctx(mode="teach"), stance="peer")
    assert out["intervention"] == "reciprocate"


# ── 7. oracle + frustration → diagnose (coerced; never encourage) ─────────────

def test_oracle_frustration_yields_diagnose_not_encourage():
    p = _plan(affect="frustration", intervention="co_reason")
    out = _rules_overlay(p, _ctx(), stance="oracle")
    assert out["intervention"] != "encourage"
    assert out["intervention"] in _ORACLE_INTERVENTIONS


# ── 8. peer + frustration + repeatedError → encourage (affect beats error) ───

def test_frustration_beats_repeated_error():
    p = _plan(affect="frustration", intervention="co_reason")
    out = _rules_overlay(p, _ctx(repeated_error=True), stance="peer")
    assert out["intervention"] == "encourage"


# ── 9. peer + curious + repeatedError → diagnose (no affect override) ─────────

def test_repeated_error_still_fires_without_affect_override():
    p = _plan(affect="curious", intervention="co_reason")
    out = _rules_overlay(p, _ctx(repeated_error=True), stance="peer")
    assert out["intervention"] == "diagnose"
