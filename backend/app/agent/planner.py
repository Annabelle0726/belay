"""
Planner component.

Decides, before any reply is written: how the student seems to be feeling, and
the single best pedagogical move. An LLM call reads affect + situation; a
deterministic rules overlay then enforces hard peer-tutoring invariants that
should never be left to chance.
"""
from __future__ import annotations

from ..core.domain import get_active_pack
from . import context as ctx_mod
from .llm import LLMClient
from .prompts import TEACH_ADDENDUM, planner_system

_VALID_INTERVENTIONS = {
    "observe", "co_reason", "diagnose", "worked_analogy", "stretch",
    "reciprocate", "escalate", "encourage", "revisit",
}
# Oracle is an answer-giver: no escalate (Sol is the authority) and no
# reciprocate (Sol answers rather than handing the work back). "encourage" and
# "revisit" are also peer-only — oracle's catch-all coerces them to "diagnose".
# Enforcing this deterministically guarantees flag_escalate can never fire for
# oracle, and revisit (spaced retrieval) stays a peer-stance feature.
_ORACLE_INTERVENTIONS = {"observe", "co_reason", "diagnose", "worked_analogy", "stretch"}

# Affective states that signal a student needs meta-affective support (peer only).
NEEDS_SUPPORT = {"frustration", "disengaged"}


def _rules_overlay(plan: dict, ctx: dict, stance: str = "peer") -> dict:
    """Deterministic guardrails on top of the model's choice."""
    mode = ctx["mode"]
    result = ctx["last_result"]
    sig = ctx["attempt_signals"]

    # Teach mode is always reciprocal — but reciprocate is a peer-only move.
    if mode == "teach" and stance != "oracle":
        plan["intervention"] = "reciprocate"
        return plan

    # On a solved exercise, offer a stretch rather than more help. Oracle has no
    # reciprocate, so it is excluded from the "leave it alone" set there.
    keep_on_goal = ("stretch", "observe") if stance == "oracle" else ("stretch", "observe", "reciprocate")
    if isinstance(result, dict) and result.get("goal_met"):
        if plan.get("intervention") not in keep_on_goal:
            plan["intervention"] = "stretch"
            plan["planner_note"] = "they hit the goal — offer a stretch rather than more help"
    else:
        # ── Affect-adaptive rules (peer only; oracle coerces encourage→diagnose) ─
        # These fire AFTER teach/goal_met branches (which return early or own the
        # turn) and BEFORE the repeatedError check, so negative affect takes
        # precedence over the error signal when the student is emotionally stuck.
        if stance != "oracle":
            affect = plan.get("affective_state")
            if affect == "disengaged":
                plan["intervention"] = "encourage"
                plan["planner_note"] = (
                    "disengaged — re-engage with a small, low-stakes next step")
            elif affect == "frustration":
                plan["intervention"] = "encourage"
                plan["planner_note"] = (
                    "frustration — affirm real progress, normalize, one concrete next step")
            elif affect == "flow":
                if plan.get("intervention") in ("diagnose", "worked_analogy"):
                    plan["intervention"] = "observe"
                    plan["planner_note"] = "in flow — stay out of the way"

        # repeatedError fires only when affect did NOT claim the turn.
        if plan.get("intervention") not in ("encourage",) and sig.get("repeatedError"):
            # Same error twice running — name the cause, don't just nudge.
            if plan.get("intervention") in ("observe", "co_reason"):
                plan["intervention"] = "diagnose"
                plan["planner_note"] = "same error repeated — name the likely cause + next step"

        # Spaced revisit — lowest precedence: only claims calm observe/co_reason turns.
        # teach/goal_met/encourage/diagnose all fire first; this fires last.
        if (plan.get("intervention") in ("observe", "co_reason")
                and ctx.get("due_review")):
            cid = ctx["due_review"][0]["id"]
            plan["intervention"] = "revisit"
            plan["revisit_concept"] = cid
            plan["target_concept"] = cid
            plan["planner_note"] = (
                f"spaced check — {cid} was shaky earlier and this exercise builds on it"
            )

    if stance == "oracle":
        # Coerce any peer-only move (escalate/reciprocate) into the answer-giver's menu.
        if plan.get("intervention") not in _ORACLE_INTERVENTIONS:
            plan["intervention"] = "diagnose"
    elif plan.get("intervention") not in _VALID_INTERVENTIONS:
        plan["intervention"] = "co_reason"
    return plan


def plan(ctx: dict, llm: LLMClient, stance: str = "peer") -> dict:
    persona = get_active_pack().persona
    base = planner_system(persona, stance)
    system = base + (("\n\n" + TEACH_ADDENDUM) if ctx["mode"] == "teach" else "")
    out = llm.json(role="planner", tier="fast", system=system,
                   user=ctx_mod.serialize(ctx), max_tokens=400)
    plan = {
        "affective_state": out.get("affective_state", "curious"),
        "affect_reasoning": out.get("affect_reasoning", ""),
        "intervention": out.get("intervention", "co_reason"),
        "target_concept": out.get("target_concept", ctx["exercise"]["concept"]),
        "planner_note": out.get("planner_note", ""),
        # Per-agent confidence: the Planner's certainty in its affect read +
        # chosen move. One leg of the confidence trajectory Step 4 calibrates.
        "confidence": float(out.get("confidence", 0.7)),
    }
    return _rules_overlay(plan, ctx, stance)
