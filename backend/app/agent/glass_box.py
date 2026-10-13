# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic student-facing account of visible evidence and help choice."""

from __future__ import annotations

_APPROACH = {
    "clarify": "I asked which part you mean so I do not guess your question.",
    "co_reason": "I asked a question so we can reason through the next step together.",
    "revisit": "I returned to this idea with a different question before suggesting a change.",
    "diagnose": "I focused on a possible cause and a small next check.",
    "worked_analogy": "I used a related example to help explain the idea.",
    "encourage": "I suggested a manageable next step.",
    "stretch": "I offered a follow-up question to extend the result.",
    "reflect": "I asked you to connect this step with your learning goal.",
    "reciprocate": "I responded to the question you asked about this exercise.",
    "observe": "I kept the response brief so you can continue your work.",
    "escalate": "I avoided guessing and suggested another source of help.",
}


def student_glass_box(released: dict, payload: dict) -> dict[str, str]:
    """Use only known student-visible inputs; never echo internal model reasoning."""
    result = payload.get("result")
    pack = result.get("pack") if isinstance(result, dict) else None
    recent = payload.get("recent")
    submitted_question = isinstance(recent, list) and any(
        isinstance(item, dict)
        and item.get("who") in {"student", "user"}
        and isinstance(item.get("text"), str)
        and bool(item["text"].strip())
        for item in recent
    )
    if isinstance(pack, dict) and pack.get("execution_status") == "student_error":
        evidence = "The code run supplied with this request reported an error."
    elif isinstance(result, dict) and result.get("goalMet") is False:
        evidence = (
            "The run supplied with this request completed, and an exercise check needs attention."
        )
    elif isinstance(result, dict) and result.get("ok") is True:
        evidence = "The code run supplied with this request completed."
    elif submitted_question:
        evidence = "I used the question you submitted about this exercise."
    else:
        evidence = "I did not have a confirmed code run to refer to."
    if payload.get("reply_to"):
        evidence = "I referred to the Sol reply you quoted and your follow-up. " + evidence
    intervention = released.get("intervention")
    return {
        "evidence": evidence,
        "approach": _APPROACH.get(
            intervention if isinstance(intervention, str) else "",
            "I chose a small next step based on the information available.",
        ),
    }
