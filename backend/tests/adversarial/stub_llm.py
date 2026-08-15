# SPDX-License-Identifier: AGPL-3.0-only
"""
Stub LLM for deterministic testing of the governance gate.
"""

from __future__ import annotations

from app.agent.llm import LLMClient


class StubLLM(LLMClient):
    """
    Stub LLM that returns valid JSON responses for the tutor loop.

    This allows testing the governance gate end-to-end without
    making real API calls. The stub returns deterministic responses
    that exercise the full tutor pipeline.
    """

    name: str = "stub-llm"

    def __init__(self):
        self.calls = []  # Track which roles were called

    def json(
        self,
        *,
        role: str,
        tier: str,
        system: str,
        user: str,
        max_tokens: int = 800,
        reasoning_effort: str | None = None,
    ) -> dict:
        """Return a valid JSON response for the given role."""
        self.calls.append({"role": role, "tier": tier})

        # Planner response
        if role == "planner":
            return {
                "affective_state": "curious",
                "affect_reasoning": "Student is seeking help, maintain encouraging tone",
                "intervention": "co_reason",
                "target_concept": "groupby_mean",
                "planner_note": "Student stuck on grouping operation",
                "confidence": 0.8,
            }

        # Reasoner response (does NOT contain solution)
        if role == "reasoner":
            return {
                "message": "Let's think about what operation combines categories. What should each category collapse to?",
                "check_question": "What single number summarizes each category?",
                "confidence": 0.75,
                "grasped": ["groupby"],
                "shaky": ["aggregation"],
                "misconception_id": None,
            }

        # Self-evaluation response
        if role == "self_eval":
            return {
                "needs_revision": False,
                "confidence": 0.8,
                "leak_risk": "none",
                "self_critique": "The draft is helpful and doesn't leak the solution",
                "reasons": [],
                "goal_alignment": 0.7,
            }

        # Fallback
        return {"message": "I understand. Let me help you think through this."}
