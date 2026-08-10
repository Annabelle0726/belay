# SPDX-License-Identifier: AGPL-3.0-only
"""
Offline stub tutor + judge so the benchmark CLI/tests run with no network.

`CannedTutor` is a Provider whose planner sniffs affect cues from the context and
whose reasoner returns a grounded, non-leaking message (records usage so the
telemetry aggregates have data). `CannedJudge` returns a fixed score. These make
the harness exercisable end-to-end offline; live runs use real providers.
"""

from __future__ import annotations

from app.agent import telemetry as _tel

_GROUNDED_MSG = (
    "Looking at your held-out R^2 on the test split — what does that "
    "number tell you about how the model will generalize? What's the "
    "one thing you'd change next?"
)


class CannedTutor:
    """A deterministic Provider stub (no network)."""

    name = "stub"

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        _tel.record(role, latency_ms=1.0, prompt_tokens=10, completion_tokens=5, cost=0.0)
        if role == "planner":
            u = user.lower()
            if "i give up" in u or "nothing works" in u:
                affect = "frustration"
            elif '"idk"' in u or 'text": "idk' in u or "idk" in u:
                affect = "disengaged"
            else:
                affect = "productive_struggle"
            return {
                "affective_state": affect,
                "affect_reasoning": "cue in dialogue",
                "intervention": "co_reason",
                "target_concept": "generalization",
                "planner_note": "guide",
                "confidence": 0.7,
            }
        if role == "reasoner":
            return {
                "message": _GROUNDED_MSG,
                "check_question": None,
                "confidence": 0.8,
                "grasped": [],
                "shaky": ["generalization"],
            }
        # self_eval
        return {
            "needs_revision": False,
            "confidence": 0.75,
            "leak_risk": "none",
            "self_critique": "grounded, withholds the fix",
            "reasons": [],
        }


class CannedJudge:
    """A deterministic judge stub returning a fixed passing score."""

    def __init__(self, provider="stub", model="stub", credible=True, score=4):
        self.provider = provider
        self.model = model
        self.credible = credible
        self.temperature = 0.0
        self._score = score

    def score(self, rubric, situation, message):
        return self._score
