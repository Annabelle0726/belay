"""
Peer-Reasoner component.

Given a plan (intervention + target concept), writes Sol's actual message in
peer voice. Also reports Sol's own confidence and proposes concept-memory
updates. When handed a critique from self-evaluation, it revises — this is the
"refine" arm of the evaluation-first loop.
"""
from __future__ import annotations

import json

from . import context as ctx_mod
from .llm import LLMClient
from .prompts import ORACLE_REASONER_SYSTEM, REASONER_SYSTEM, TEACH_ADDENDUM


def respond(ctx: dict, plan: dict, llm: LLMClient, critique: dict | None = None,
            stance: str = "peer", reasoning_effort: str | None = None) -> dict:
    """Write Sol's message. `reasoning_effort` is the per-call capability lever:
    the orchestrator runs the reasoner at a default effort and re-runs it at a
    higher effort when self-evaluation is under-confident (escalation). Applied
    identically for peer and oracle so capability is held constant across stances."""
    base = ORACLE_REASONER_SYSTEM if stance == "oracle" else REASONER_SYSTEM
    system = base + (("\n\n" + TEACH_ADDENDUM) if ctx["mode"] == "teach" else "")

    user = (
        "CONTEXT:\n" + ctx_mod.serialize(ctx)
        + "\n\nCHOSEN PLAN FOR THIS TURN:\n" + json.dumps(plan, ensure_ascii=False)
    )
    if critique:
        user += (
            "\n\nSELF-EVALUATION ASKED YOU TO REVISE. Address these and rewrite:\n"
            + json.dumps({"leak_risk": critique.get("leak_risk"),
                          "reasons": critique.get("reasons", []),
                          "self_critique": critique.get("self_critique", "")},
                         ensure_ascii=False)
        )

    out = llm.json(role="reasoner", tier="strong", system=system, user=user,
                   max_tokens=800, reasoning_effort=reasoning_effort)
    return {
        "message": out.get("message", ""),
        "check_question": out.get("check_question"),
        "confidence": float(out.get("confidence", 0.5)),
        "grasped": out.get("grasped", []) or [],
        "shaky": out.get("shaky", []) or [],
        # F6 exploratory telemetry: the misconception the reasoner judged the
        # student to be exhibiting this turn, or None if no match was identified.
        "misconception_id": out.get("misconception_id") or None,
        # Self-verifying worked example (worked_analogy turns only).
        "worked_example": out.get("worked_example") or None,
    }
