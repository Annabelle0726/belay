"""
Sol behavioral evaluations (the "evaluation-first" claim, operationalized).

Two layers:
  1. Deterministic invariants that must ALWAYS hold (no solution leak; just-
     solved -> stretch/observe; teach -> reciprocate; answer-seeking ->
     redirect). These run against the real model output.
  2. An optional LLM-graded rubric (groundedness + calibration) that scores the
     produced message; asserts a minimum bar.

Requires ANTHROPIC_API_KEY; without it the module skips so CI stays green
offline. Run: pytest -q tests/evals/sol_behavior_evals.py
"""
from __future__ import annotations

import json
import os
import sys

import pytest

from app.agent import get_llm, run_turn
from app.store import InMemoryStore

sys.path.insert(0, os.path.dirname(__file__))
from fixtures import FIXTURES  # noqa: E402  (path-independent: works under pytest and as a script)

_RUN = bool(os.environ.get("RUN_LLM_EVALS"))
pytestmark = pytest.mark.skipif(not _RUN, reason="set RUN_LLM_EVALS=1 (with a reachable LLM) to run behavioral evals")


def _run(name):
    return run_turn(FIXTURES[name], get_llm(), InMemoryStore())


# ---- Layer 1: deterministic invariants on real output -----------------------

def test_never_leaks_solution_across_fixtures():
    for name in FIXTURES:
        out = _run(name)
        # governance must never let a full solution through
        assert "entangle q0 q1" not in out["message"] or out["governance"] == "withholding_solution"
        assert out["components"]["governance"]["blocked"] is False or out["governance"] == "withholding_solution"


def test_just_solved_offers_stretch_or_observe():
    out = _run("just_solved")
    assert out["intervention"] in ("stretch", "observe", "reciprocate")


def test_teach_mode_is_reciprocal():
    out = _run("teach_mode")
    assert out["intervention"] == "reciprocate"


def test_answer_seeking_redirects():
    out = _run("answer_seeking")
    assert out["governance"] in ("redirect_answer_seeking", "withholding_solution")


def test_worked_example_is_always_verified_when_shown():
    """If a worked example appears in the message, it must be verifiable:
    compiles AND does not solve the current exercise.  This catches any
    regression where the orchestrator shows an unverified snippet."""
    from app.quantum.worked_example import verify_worked_example
    import re

    out = _run("stuck_wants_example")
    msg = out["message"]

    # Extract fenced code blocks from the message
    fenced = re.findall(r"```[a-zA-Z]*\n(.*?)```", msg, re.DOTALL)
    if not fenced:
        # No snippet shown — acceptable (model chose not to include an example)
        return

    from app.curriculum import get_exercise
    bell = get_exercise("bell")
    for src in fenced:
        result = verify_worked_example(
            {"source": src.strip()},
            bell["target"],
            bell["tol"],
        )
        assert result["ok"], (
            f"A shown worked example failed verification: "
            f"reason={result['reason']!r} src={src!r}"
        )


def test_frustration_gets_encourage_intervention():
    """Planner overlay must route frustration to encourage (deterministic invariant)."""
    out = _run("frustrated")
    assert out["intervention"] == "encourage", (
        f"expected encourage on frustrated fixture, got {out['intervention']!r}")


def test_disengaged_gets_encourage_intervention():
    """Planner overlay must route disengaged to encourage (deterministic invariant)."""
    out = _run("disengaged")
    assert out["intervention"] == "encourage", (
        f"expected encourage on disengaged fixture, got {out['intervention']!r}")


# ---- Layer 2: LLM-graded rubric ---------------------------------------------

_GRADER = """You grade a peer tutor's single message. Given the student's situation and the
tutor's message, score two properties 1-5:
  grounded   - references the student's actual code/result rather than generic advice
  calibrated - the tutor's confidence/assertiveness fits how ambiguous things are
Respond with ONLY JSON: {"grounded": int, "calibrated": int, "note": "one clause"}."""


def _grade(situation: dict, message: str) -> dict:
    llm = get_llm()
    raw = llm.json(role="grader", tier="fast", system=_GRADER,
                   user=json.dumps({"situation": situation, "tutor_message": message}),
                   max_tokens=200)
    return raw


def test_progressing_message_is_grounded_and_calibrated():
    out = _run("progressing")
    fx = FIXTURES["progressing"]
    grade = _grade({"source": fx["source"], "result": fx["result"], "signals": fx["signals"]},
                   out["message"])
    assert grade["grounded"] >= 3, grade
    assert grade["calibrated"] >= 3, grade


# ---- Layer 2 extension: encourage quality -----------------------------------

_ENCOURAGE_GRADER = """You evaluate a peer-tutor's encourage message for a frustrated or disengaged student.
Score three properties 1–5:
  grounded    - Sol references something SPECIFIC from the student's code or run (not "you're doing great" — it must name what they actually did)
  concrete    - Sol gives a single clear next step (not vague "keep trying")
  no_solution - 5 = no full solution given; 1 = full solution handed over
Respond with ONLY JSON: {"grounded": int, "concrete": int, "no_solution": int, "note": "one clause"}."""


def _grade_encourage(situation: dict, message: str) -> dict:
    llm = get_llm()
    return llm.json(role="grader", tier="fast", system=_ENCOURAGE_GRADER,
                    user=json.dumps({"situation": situation, "tutor_message": message}),
                    max_tokens=200)


def test_frustration_gets_grounded_support():
    """Sol's encourage on frustrated must: affirm specific code/run, normalize, give one step."""
    out = _run("frustrated")
    fx = FIXTURES["frustrated"]
    grade = _grade_encourage(
        {"source": fx["source"], "result": fx["result"],
         "recent": fx["recent"], "signals": fx["signals"]},
        out["message"],
    )
    assert grade["grounded"]    >= 3, f"grounded={grade['grounded']} — {grade.get('note')}"
    assert grade["concrete"]    >= 3, f"concrete={grade['concrete']} — {grade.get('note')}"
    assert grade["no_solution"] >= 4, f"no_solution={grade['no_solution']} — {grade.get('note')}"


def test_disengaged_gets_reengagement():
    """Sol's encourage on disengaged must: affirm something specific, give one small next step."""
    out = _run("disengaged")
    fx = FIXTURES["disengaged"]
    grade = _grade_encourage(
        {"source": fx["source"], "result": fx["result"],
         "recent": fx["recent"], "signals": fx["signals"]},
        out["message"],
    )
    assert grade["grounded"]    >= 3, f"grounded={grade['grounded']} — {grade.get('note')}"
    assert grade["concrete"]    >= 3, f"concrete={grade['concrete']} — {grade.get('note')}"
    assert grade["no_solution"] >= 4, f"no_solution={grade['no_solution']} — {grade.get('note')}"


# ── Layer 1 + 2 extension: revisit quality ───────────────────────────────────

_REVISIT_GRADER = """You evaluate a peer-tutor's revisit message for a student with a prior shaky concept.
A revisit turn must: (1) acknowledge the concept warmly without shaming, (2) pose
EXACTLY ONE retrieval or prediction question grounded in the current exercise,
(3) NOT re-explain the concept, (4) NOT give the answer or a full solution.
Score three properties 1–5:
  grounded    - the question is grounded in the student's current code or exercise (not abstract)
  question    - the message contains exactly one clear question (5=one question; 1=no question or multiple)
  no_solution - 5 = no answer given; 1 = full answer handed over
Respond with ONLY JSON: {"grounded": int, "question": int, "no_solution": int, "note": "one clause"}."""


def _grade_revisit(situation: dict, message: str) -> dict:
    llm = get_llm()
    return llm.json(role="grader", tier="fast", system=_REVISIT_GRADER,
                    user=json.dumps({"situation": situation, "tutor_message": message}),
                    max_tokens=200)


def test_revisit_is_a_grounded_question_not_an_explanation():
    """When superposition is shaky and due, Sol must ask ONE retrieval question — not re-explain."""
    from app.store import InMemoryStore
    store = InMemoryStore()
    pid = FIXTURES["prior_shaky_superposition"]["participant_id"]
    # Pre-populate LearnerState.concepts with superposition=shaky so
    # build_context sees due_review=[superposition] on the bell exercise.
    store.save_learner_state(pid, {
        "grasped": [], "shaky": [], "attempts": 0,
        "concepts": {
            "superposition": {
                "state": "shaky", "evidence": 1,
                "last_seen": "2026-06-02T00:00:00+00:00",
                "last_review": None, "last_review_ex": None,
            }
        },
    })
    out = run_turn(FIXTURES["prior_shaky_superposition"], get_llm(), store)
    assert out["intervention"] == "revisit", (
        f"expected revisit intervention, got {out['intervention']!r}")
    fx = FIXTURES["prior_shaky_superposition"]
    grade = _grade_revisit(
        {"source": fx.get("source"), "result": fx.get("result")},
        out["message"],
    )
    assert grade["grounded"]    >= 3, f"grounded={grade['grounded']} — {grade.get('note')}"
    assert grade["question"]    >= 3, f"question={grade['question']} — {grade.get('note')}"
    assert grade["no_solution"] >= 4, f"no_solution={grade['no_solution']} — {grade.get('note')}"


if __name__ == "__main__":
    if not _RUN:
        print("SKIP behavioral evals (set RUN_LLM_EVALS=1 with a reachable LLM to run)")
    else:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print("PASS", name)
        print("behavioral evals: all passed")
