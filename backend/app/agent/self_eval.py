"""
Self-Evaluation component.

Re-reads Sol's draft before it reaches the student and scores it against the
stance-appropriate rubric. Its verdict (`needs_revision`) drives the refine
loop; its calibrated confidence is what the glass box surfaces and what
governance consults. This is the heart of the "evaluation-first" stance: the
agent critiques itself prior to acting.

The loop runs for BOTH peer and oracle (matched capability/effort); only the
rubric differs. The peer rubric refines toward NOT-answering (no-leak,
preserves-struggle); the oracle rubric refines toward a correct answer
(grounded/correct/clear) and never penalizes handing over the solution.
"""
from __future__ import annotations

import json

from ..core.domain import get_active_pack
from .llm import LLMClient
from .prompts import selfeval_system


def evaluate(ctx: dict, plan: dict, draft: dict, llm: LLMClient,
             stance: str = "peer") -> dict:
    # Goal alignment is a QUALITY signal behind the floors; only honored goals get
    # a criterion (the gate + wellbeing floor remain supreme and run regardless).
    system = selfeval_system(get_active_pack().persona, stance, goals=ctx.get("goals"))
    user = json.dumps({
        "exercise": ctx["exercise"],
        "student_state": {
            "current_functional_model": ctx["current_functional_model"],
            "last_result": ctx["last_result"],
            "attempt_signals": ctx["attempt_signals"],
        },
        "chosen_plan": plan,
        "sol_draft": {"message": draft.get("message"),
                      "check_question": draft.get("check_question"),
                      "stated_confidence": draft.get("confidence")},
    }, ensure_ascii=False, indent=2)

    out = llm.json(role="self_eval", tier="fast", system=system,
                   user=user, max_tokens=400)
    return {
        "needs_revision": bool(out.get("needs_revision", False)),
        "confidence": float(out.get("confidence", draft.get("confidence", 0.5))),
        "leak_risk": out.get("leak_risk", "none"),
        "self_critique": out.get("self_critique", ""),
        "reasons": out.get("reasons", []) or [],
        # Goal-alignment quality signal (None when no honored goals are set).
        "goal_alignment": out.get("goal_alignment"),
    }
