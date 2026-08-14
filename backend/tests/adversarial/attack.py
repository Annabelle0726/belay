# SPDX-License-Identifier: AGPL-3.0-only
"""
Stub LLM for deterministic testing of the governance gate.

Attack classes implemented (scripted/reproducible without fine-tuned model):
- Direct override attempts (3 variants)
- Role-play framing (3 variants)
- Incremental piecewise extraction (2 variants)
- Obfuscation (3 variants: base64, translation, narrative)
- Context manipulation (2 variants: authorization, emergency)

Attack classes explicitly NOT implemented (require fine-tuned adversary model):
- Learned adversarial policy (requires fine-tuned model)
- Multi-agent collusion (requires multiple agents)

"""

from __future__ import annotations

from typing import Any

from app.agent.llm import LLMClient
from app.agent.orchestrator import run_turn
from app.core.registry import get_active_pack
from app.store import InMemoryStore
from conftest import _payload


class Attack:
    """Represents a single adversarial attack strategy."""

    def __init__(
            self,
            name: str,
            category: str,
            description: str,
            student_messages: list[str],
            expected_leak: bool = False,
            paper_reference: str = "",
    ):
        self.name = name
        self.category = category
        self.description = description
        self.student_messages = student_messages
        self.expected_leak = expected_leak
        self.paper_reference = paper_reference

    def run(self, llm: LLMClient, exercise_id: str = "ds-foundations") -> dict[str, Any]:
        """Execute the attack through the full tutor pipeline."""
        pack = get_active_pack()
        exercise = pack.get_exercise(exercise_id)
        store = InMemoryStore()

        # Run each message as a separate turn
        final_result = None
        for i, msg in enumerate(self.student_messages):
            payload = _payload(
                pid=f"adv_{hash(self.name)}_{i}",
                student_text=msg,
                stance="peer",
                exercise_id=exercise_id,
            )
            result = run_turn(payload, llm, store)
            final_result = result

        # Analyze the final result for leaks
        governance_flag = final_result.get("governance", "none")
        message = final_result.get("message", "")

        leaked = governance_flag == "withholding_solution"
        solution_leaked = self._contains_solution(message, exercise)

        return {
            "success": solution_leaked or not leaked,
            "message": message,
            "governance_flag": governance_flag,
            "leaked": solution_leaked or leaked,
            "evidence": self._extract_evidence(final_result),
            "turns": len(self.student_messages),
        }

    def _contains_solution(self, message: str, exercise: dict) -> bool:
        """Check if the message contains the actual solution code."""
        pack = get_active_pack()
        evidence = pack.leak_evidence(message, exercise)
        return evidence.is_solution or evidence.prose_disclosure

    def _extract_evidence(self, result: dict) -> list[str]:
        """Extract governance evidence from the result."""
        components = result.get("components", {})
        governance_data = components.get("governance", {})
        return governance_data.get("reasons", [])
