"""
Governance component — the last gate before a reply reaches the student.

Mostly deterministic on purpose: safety shouldn't depend on the model
behaving. Its sharpest tool reuses our own grader — any code Sol proposes is
run through the functional-model backend against the current exercise's target,
and if it would actually solve the exercise, that's a full-solution leak. The
offending snippet is stripped and the turn is flagged. This makes the HARD RULE
("never hand over the solution") enforceable rather than merely requested.

Governance flags map onto the values the front-end glass box already renders:
  none | withholding_solution | redirect_answer_seeking | encourage_tone | flag_escalate

The snippet extraction + goal-meeting check live in quantum/leak_check.py so
governance and analysis/measures.py call the SAME function and can never drift.
"""
from __future__ import annotations

import re

from ..quantum.leak_check import FENCE, OP_LINE, candidate_snippets, is_goal_meeting

_ANSWER_SEEKING = re.compile(
    r"\b(just tell me|what'?s the answer|give me the (answer|code|solution)|"
    r"show me the (code|solution)|solve it for me)\b",
    re.IGNORECASE,
)


def _student_asked_for_answer(ctx: dict) -> bool:
    recent = ctx.get("recent_dialogue", [])
    for turn in reversed(recent):
        if turn.get("who") == "student":
            return bool(_ANSWER_SEEKING.search(turn.get("text", "")))
    return False


def check(ctx: dict, plan: dict, draft: dict, evaluation: dict,
          stance: str = "peer") -> dict:
    exercise = ctx["_exercise_full"]
    flag = "none"
    blocked = False
    reasons = []

    if plan.get("intervention") == "escalate":
        flag = "flag_escalate"

    # Strong, deterministic leak check via the grader itself.
    # Oracle stance is explicitly allowed to hand over the solution.
    if stance == "peer" and is_goal_meeting(
            draft.get("message", ""), exercise["target"], exercise["tol"]):
        blocked = True
        flag = "withholding_solution"
        reasons.append("draft contained code that solves the exercise")

    # Redirecting answer-seeking is a PEER move. In oracle, answering the request
    # is the whole point, so an answered answer-seeking turn must read as "none"
    # (Step 4's realized_handoff captures the oracle hand-off instead).
    if stance == "peer" and _student_asked_for_answer(ctx):
        # If they pushed for the answer, the turn must read as a redirect.
        if flag in ("none",):
            flag = "redirect_answer_seeking"

    return {"flag": flag, "block": blocked, "reasons": reasons}


def safe_rewrite(draft: dict, gov: dict, exercise: dict) -> dict:
    """Strip solution code; leave the surrounding peer prose; add a redirect."""
    msg = draft.get("message", "")
    msg = FENCE.sub("", msg)
    kept = [ln for ln in msg.split("\n") if not OP_LINE.match(ln)]
    msg = "\n".join(kept).strip()
    redirect = ("Actually — I don't want to just paste the whole thing, that's the part "
                "worth working out. What's the *one* operation you think comes next, and why?")
    draft = dict(draft)
    draft["message"] = (msg + "\n\n" + redirect).strip() if msg else redirect
    draft["check_question"] = draft.get("check_question") or "What do you think the next single step is?"
    # If we had to suppress a solution, Sol shouldn't also claim high confidence.
    draft["confidence"] = min(float(draft.get("confidence", 0.5)), 0.6)
    return draft
