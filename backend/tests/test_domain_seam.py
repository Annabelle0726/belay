# SPDX-License-Identifier: AGPL-3.0-only
"""
Domain-seam test: the dependency-free `_skeleton` pack plus a stub LLM completes
one full orchestrated turn. Proves the core loop (context → planner → reasoner →
self-eval → governance → memory → trace) runs against ANY `DomainPack`, with no
concrete domain and no third-party deps.
"""

from __future__ import annotations

import json

from app.agent import run_turn
from app.core.registry import get_active_pack
from app.store import InMemoryStore


class StubLLM:
    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {
                "affective_state": "curious",
                "affect_reasoning": "exploring",
                "intervention": "co_reason",
                "target_concept": "echo concept",
                "planner_note": "nudge",
                "confidence": 0.7,
            }
        if role == "reasoner":
            return {
                "message": "What output do you expect to see?",
                "check_question": None,
                "confidence": 0.75,
                "grasped": [],
                "shaky": ["echo concept"],
            }
        if role == "self_eval":
            return {
                "needs_revision": False,
                "confidence": 0.7,
                "leak_risk": "none",
                "self_critique": "grounded",
                "reasons": [],
            }
        raise AssertionError(role)


def _payload(pid="p_seam"):
    pack = get_active_pack()
    return {
        "participant_id": pid,
        "exercise": pack.get_exercise("echo-1"),
        "event": "run",
        "mode": "study",
        "stance": "peer",
        "source": "print('...')",
        "result": {
            "ok": True,
            "goalMet": False,
            "metric": None,
            "pack": {"id": "_skeleton", "summary": "echo: no match"},
        },
        "recent": [],
        "signals": None,
    }


def test_skeleton_pack_completes_a_turn(monkeypatch):
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    assert get_active_pack().id == "_skeleton"

    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(), store)

    for k in (
        "affective_state",
        "confidence",
        "intervention",
        "message",
        "governance",
        "memory",
        "components",
    ):
        assert k in out, f"missing {k}"
    assert out["components"]["pack"] == "_skeleton"
    # exactly one trace event, pack-tagged
    row = json.loads(store.export_jsonl("p_seam"))
    assert row["payload"]["telemetry"]["pack"] == "_skeleton"
    assert row["stance"] == "peer"
