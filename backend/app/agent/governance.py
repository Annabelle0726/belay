"""
Governance component — the last gate before a reply reaches the student.

Mostly deterministic on purpose: safety shouldn't depend on the model behaving.
Its sharpest tool reuses the domain's own grader — any code the tutor proposes is
run through the active pack's executable oracle against the current exercise's
goal, and if it would actually solve the exercise, that's a full-solution leak.
The offending snippet is stripped and the turn is flagged. This makes the HARD
RULE ("never hand over the solution") enforceable rather than merely requested.

Pack-agnostic (Phase 1a): the block/rewrite/abstain decision lives HERE and is
deterministic. It consumes `LeakEvidence` supplied by the active `DomainPack`
(`pack.leak_evidence`): the executable grader is one evidence source; the
decision is core's. The pack owns the domain-specific redaction (which surface to
strip); core owns the peer-voiced redirect that replaces it.

Note on leak heuristics: the quantum pack's leak evidence is executable-
comparison-only (it runs candidate snippets through the grader). There are no
domain-agnostic *prose*-leak heuristics to host in core today (no "the answer is
X" detector) — only the answer-seeking detector below, which reads the STUDENT's
message, not the draft. A retrieval-backed or prose-heavy pack (e.g. the 1b
data-science pack) will need prose-leak heuristics; see EXTRACTION_PLAN §(f).

Governance flags map onto the values the front-end glass box already renders:
  none | withholding_solution | redirect_answer_seeking | encourage_tone | flag_escalate
"""
from __future__ import annotations

import re

from ..core.domain import get_active_pack

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
          stance: str = "peer", pack=None) -> dict:
    pack = pack or get_active_pack()
    exercise = ctx["_exercise_full"]
    flag = "none"
    blocked = False
    reasons = []

    if plan.get("intervention") == "escalate":
        flag = "flag_escalate"

    # Strong, deterministic leak check via the domain's executable oracle.
    # Oracle stance is explicitly allowed to hand over the solution.
    if stance == "peer" and pack.leak_evidence(draft.get("message", ""), exercise).is_solution:
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


def safe_rewrite(draft: dict, gov: dict, exercise: dict, pack=None) -> dict:
    """Strip solution code; leave the surrounding peer prose; add a redirect.

    The domain-specific redaction comes from the pack (via `LeakEvidence`); the
    peer-voiced redirect and the confidence cap are the core decision. Re-derives
    the evidence from the pack (deterministic; only runs on a block).
    """
    pack = pack or get_active_pack()
    msg = pack.leak_evidence(draft.get("message", ""), exercise).redacted_message
    redirect = ("Actually — I don't want to just paste the whole thing, that's the part "
                "worth working out. What's the *one* operation you think comes next, and why?")
    draft = dict(draft)
    draft["message"] = (msg + "\n\n" + redirect).strip() if msg else redirect
    draft["check_question"] = draft.get("check_question") or "What do you think the next single step is?"
    # If we had to suppress a solution, the tutor shouldn't also claim high confidence.
    draft["confidence"] = min(float(draft.get("confidence", 0.5)), 0.6)
    return draft
