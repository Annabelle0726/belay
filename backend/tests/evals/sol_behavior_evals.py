"""
Peer-tutor behavioral evaluations (DS pack / "Robin") — the "evaluation-first"
claim, operationalized as a portable benchmark.

Two layers:
  1. Deterministic invariants that must ALWAYS hold against real model output:
     never leak (CODE or PROSE); just-solved -> stretch/observe; teach ->
     reciprocate; answer-seeking -> redirect; frustration/disengaged -> encourage.
  2. An optional LLM-graded rubric (groundedness + calibration; encourage quality;
     revisit quality) asserting a minimum bar.

Gated by RUN_LLM_EVALS (needs a reachable LLM); skips offline so the suite stays
green. Run: RUN_LLM_EVALS=1 pytest -q tests/evals/sol_behavior_evals.py
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

from app.agent import get_llm, run_turn
from app.core.domain import get_active_pack
from app.store import InMemoryStore

sys.path.insert(0, os.path.dirname(__file__))
from fixtures import FIXTURES, REVISIT_SHAKY_CONCEPT  # noqa: E402

_RUN = bool(os.environ.get("RUN_LLM_EVALS"))
pytestmark = pytest.mark.skipif(
    not _RUN, reason="set RUN_LLM_EVALS=1 (with a reachable LLM) to run behavioral evals")

_PACK = get_active_pack()


def _run(name):
    return run_turn(FIXTURES[name], get_llm(), InMemoryStore())


# ---- Layer 1: deterministic invariants on real output -----------------------

def test_never_leaks_solution_across_fixtures():
    """For EVERY fixture, if the produced message leaks the solution — by code
    (executable oracle) OR by prose disclosure — governance must have blocked it.
    Includes the prose-bait fixture, so this covers prose leaks, not only code."""
    for name in FIXTURES:
        out = _run(name)
        ev = _PACK.leak_evidence(out["message"], FIXTURES[name]["exercise"])
        if ev.is_solution or ev.prose_disclosure:
            assert out["governance"] == "withholding_solution", (
                f"{name}: leak slipped past governance (is_solution={ev.is_solution}, "
                f"prose={ev.prose_disclosure})")
        # And the glass-box flag stays consistent with the blocking decision.
        assert (out["components"]["governance"]["blocked"] is False
                or out["governance"] == "withholding_solution"), name


def test_just_solved_offers_stretch_or_observe():
    assert _run("just_solved")["intervention"] in ("stretch", "observe", "reciprocate")


def test_teach_mode_is_reciprocal():
    assert _run("teach_mode")["intervention"] == "reciprocate"


def test_answer_seeking_redirects():
    assert _run("answer_seeking")["governance"] in ("redirect_answer_seeking", "withholding_solution")


def test_worked_example_is_always_verified_when_shown():
    """Any fenced snippet shown must verify (runs + does not solve the exercise)."""
    out = _run("stuck_wants_example")
    fenced = re.findall(r"```[a-zA-Z0-9_+\-]*\n(.*?)```", out["message"], re.DOTALL)
    if not fenced:
        return  # model chose not to include an example — acceptable
    ex = FIXTURES["stuck_wants_example"]["exercise"]
    for src in fenced:
        result = _PACK.verify_worked_example({"source": src.strip()}, ex)
        assert result["ok"], f"shown example failed verification: reason={result['reason']!r}"


def test_frustration_gets_encourage_intervention():
    assert _run("frustrated")["intervention"] == "encourage"


def test_disengaged_gets_encourage_intervention():
    assert _run("disengaged")["intervention"] == "encourage"


# ---- Layer 2: LLM-graded rubric ---------------------------------------------

_GRADER = """You grade a peer tutor's single message. Given the student's situation and the
tutor's message, score two properties 1-5:
  grounded   - references the student's actual code/result rather than generic advice
  calibrated - the tutor's confidence/assertiveness fits how ambiguous things are
Respond with ONLY JSON: {"grounded": int, "calibrated": int, "note": "one clause"}."""


def _grade(situation: dict, message: str) -> dict:
    return get_llm().json(role="grader", tier="fast", system=_GRADER,
                          user=json.dumps({"situation": situation, "tutor_message": message}),
                          max_tokens=200)


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
  grounded    - the tutor references something SPECIFIC from the student's code or run (not "you're doing great")
  concrete    - the tutor gives a single clear next step (not vague "keep trying")
  no_solution - 5 = no full solution given; 1 = full solution handed over
Respond with ONLY JSON: {"grounded": int, "concrete": int, "no_solution": int, "note": "one clause"}."""


def _grade_encourage(situation: dict, message: str) -> dict:
    return get_llm().json(role="grader", tier="fast", system=_ENCOURAGE_GRADER,
                          user=json.dumps({"situation": situation, "tutor_message": message}),
                          max_tokens=200)


def _check_encourage(name):
    out = _run(name)
    fx = FIXTURES[name]
    grade = _grade_encourage(
        {"source": fx["source"], "result": fx["result"],
         "recent": fx["recent"], "signals": fx["signals"]}, out["message"])
    assert grade["grounded"] >= 3, f"grounded={grade['grounded']} — {grade.get('note')}"
    assert grade["concrete"] >= 3, f"concrete={grade['concrete']} — {grade.get('note')}"
    assert grade["no_solution"] >= 4, f"no_solution={grade['no_solution']} — {grade.get('note')}"


def test_frustration_gets_grounded_support():
    _check_encourage("frustrated")


def test_disengaged_gets_reengagement():
    _check_encourage("disengaged")


# ── revisit quality ───────────────────────────────────────────────────────────

_REVISIT_GRADER = """You evaluate a peer-tutor's revisit message for a student with a prior shaky concept.
A revisit turn must: (1) acknowledge the concept warmly without shaming, (2) pose
EXACTLY ONE retrieval or prediction question grounded in the current exercise,
(3) NOT re-explain the concept, (4) NOT give the answer or a full solution.
Score three properties 1–5:
  grounded    - the question is grounded in the student's current code or exercise
  question    - exactly one clear question (5=one question; 1=no question or multiple)
  no_solution - 5 = no answer given; 1 = full answer handed over
Respond with ONLY JSON: {"grounded": int, "question": int, "no_solution": int, "note": "one clause"}."""


def test_revisit_is_a_grounded_question_not_an_explanation():
    store = InMemoryStore()
    pid = FIXTURES["prior_shaky_concept"]["participant_id"]
    store.save_learner_state(pid, {
        "grasped": [], "shaky": [], "attempts": 0,
        "concepts": {REVISIT_SHAKY_CONCEPT: {
            "state": "shaky", "evidence": 1,
            "last_seen": "2026-06-02T00:00:00+00:00",
            "last_review": None, "last_review_ex": None}},
    })
    out = run_turn(FIXTURES["prior_shaky_concept"], get_llm(), store)
    assert out["intervention"] == "revisit", f"expected revisit, got {out['intervention']!r}"
    fx = FIXTURES["prior_shaky_concept"]
    grade = get_llm().json(role="grader", tier="fast", system=_REVISIT_GRADER,
                           user=json.dumps({"situation": {"source": fx.get("source"),
                                                          "result": fx.get("result")},
                                            "tutor_message": out["message"]}),
                           max_tokens=200)
    assert grade["grounded"] >= 3, grade
    assert grade["question"] >= 3, grade
    assert grade["no_solution"] >= 4, grade


if __name__ == "__main__":
    if not _RUN:
        print("SKIP behavioral evals (set RUN_LLM_EVALS=1 with a reachable LLM to run)")
    else:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print("PASS", name)
        print("behavioral evals: all passed")
