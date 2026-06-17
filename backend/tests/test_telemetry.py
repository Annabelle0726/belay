"""
Per-component usage telemetry (additive §6 `telemetry.component_usage`).

Covers the UsageMeter aggregation, the additive presence of the field in a turn,
and population from provider-reported usage via a recording stub (no network).
"""

from __future__ import annotations

import json

from app.agent import run_turn
from app.agent import telemetry as tel
from app.core.domain import get_active_pack
from app.store import InMemoryStore

_EX = get_active_pack().get_exercise("ds-foundations")


def _payload(pid="p_tel", stance="peer"):
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


class _PlainStub:
    """Reports no usage (like a test stub / a provider with no usage field)."""

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
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
                "message": "what one number per group?",
                "check_question": None,
                "confidence": 0.8,
                "grasped": [],
                "shaky": ["aggregation"],
            }
        return {
            "needs_revision": False,
            "confidence": 0.7,
            "leak_risk": "none",
            "self_critique": "ok",
            "reasons": [],
        }


class _UsageStub(_PlainStub):
    """Reports provider-style usage per call (the openai/anthropic usage field)."""

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        tel.record(role, latency_ms=5.0, prompt_tokens=100, completion_tokens=20, cost=0.001)
        return super().json(
            role=role,
            tier=tier,
            system=system,
            user=user,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )


# ── UsageMeter unit ───────────────────────────────────────────────────────────


def test_usage_meter_aggregates_per_role():
    m = tel.UsageMeter()
    m.record("reasoner", latency_ms=10.0, prompt_tokens=50, completion_tokens=5, cost=0.002)
    m.record("reasoner", latency_ms=4.0, prompt_tokens=30, completion_tokens=3, cost=0.001)
    by = m.by_component()
    assert by["reasoner"]["calls"] == 2
    assert by["reasoner"]["latency_ms"] == 14.0
    assert by["reasoner"]["prompt_tokens"] == 80
    assert by["reasoner"]["completion_tokens"] == 8
    assert abs(by["reasoner"]["cost"] - 0.003) < 1e-9


def test_usage_meter_null_when_unreported():
    m = tel.UsageMeter()
    m.record("planner", latency_ms=2.0, prompt_tokens=None, completion_tokens=None, cost=None)
    e = m.by_component()["planner"]
    assert e["calls"] == 1 and e["latency_ms"] == 2.0
    assert e["prompt_tokens"] is None and e["completion_tokens"] is None and e["cost"] is None


# ── additive field presence + population in a turn ────────────────────────────


def test_component_usage_present_and_additive():
    store = InMemoryStore()
    out = run_turn(_payload(), _PlainStub(), store)
    assert "component_usage" in out["components"]  # additive field always present
    row = json.loads(store.export_jsonl("p_tel"))
    assert "component_usage" in row["payload"]["telemetry"]


def test_component_usage_populated_from_provider_usage():
    store = InMemoryStore()
    out = run_turn(_payload(pid="p_use"), _UsageStub(), store)
    cu = out["components"]["component_usage"]
    for role in ("planner", "reasoner", "self_eval"):
        assert role in cu, f"missing {role}"
        assert cu[role]["prompt_tokens"] == 100
        assert cu[role]["completion_tokens"] == 20
        assert cu[role]["cost"] == 0.001
        assert cu[role]["latency_ms"] >= 0


def test_control_turn_has_empty_component_usage():
    store = InMemoryStore()
    out = run_turn(_payload(pid="p_ctrl", stance="control"), _UsageStub(), store)
    assert out["components"]["component_usage"] == {}


def test_meter_does_not_leak_across_turns():
    """Each turn gets a fresh meter (the wrapper sets/resets it)."""
    store = InMemoryStore()
    run_turn(_payload(pid="p_a"), _UsageStub(), store)
    out_b = run_turn(_payload(pid="p_b"), _PlainStub(), store)
    # p_b used the non-recording stub → no token data leaked from p_a's meter.
    cu = out_b["components"]["component_usage"]
    assert all(v["prompt_tokens"] is None for v in cu.values()) or cu == {}
