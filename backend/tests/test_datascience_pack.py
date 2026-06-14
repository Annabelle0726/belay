"""
Data-science pack unit tests (offline; uses the sandbox runner + numpy/pandas).

Covers the three real exercises end-to-end (run + grade), the leak paths
(executable oracle + prose-disclosure heuristic), and worked-example verification.
"""
from __future__ import annotations

import pytest

from app.packs.datascience import DataSciencePack
from app.packs.datascience.solutions import SOLUTIONS

PACK = DataSciencePack()
EXERCISE_IDS = ["ds-foundations", "ds-regression", "ds-mlp"]


# ── reference solutions pass run + grade ──────────────────────────────────────

@pytest.mark.parametrize("ex_id", EXERCISE_IDS)
def test_reference_solution_passes(ex_id):
    ex = PACK.get_exercise(ex_id)
    r = PACK.run(SOLUTIONS[ex_id]["source"], ex)
    assert r["ok"] is True, r.get("error")
    assert r["goalMet"] is True, r["pack"]["summary"]
    assert r["pack"]["id"] == "datascience"


def test_regression_metric_is_held_out_score():
    ex = PACK.get_exercise("ds-regression")
    r = PACK.run(SOLUTIONS["ds-regression"]["source"], ex)
    assert r["metric"] is not None and r["metric"] >= 0.8   # R^2 on held-out split


def test_mlp_metric_is_final_loss():
    ex = PACK.get_exercise("ds-mlp")
    r = PACK.run(SOLUTIONS["ds-mlp"]["source"], ex)
    assert r["metric"] is not None and r["metric"] <= 0.05  # MSE loss


def test_wrong_answer_fails_grade():
    ex = PACK.get_exercise("ds-foundations")
    r = PACK.run("result = {'A': 0.0, 'B': 0.0, 'C': 0.0}", ex)
    assert r["ok"] is True          # ran fine
    assert r["goalMet"] is False    # but wrong


def test_runtime_error_is_not_ok():
    ex = PACK.get_exercise("ds-foundations")
    r = PACK.run("raise ValueError('boom')", ex)
    assert r["ok"] is False
    assert r["goalMet"] is False


# ── executable leak oracle ────────────────────────────────────────────────────

def test_fenced_full_solution_is_detected_as_leak():
    ex = PACK.get_exercise("ds-foundations")
    draft = "Try this:\n```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```\n"
    ev = PACK.leak_evidence(draft, ex)
    assert ev.is_solution is True


def test_no_code_no_executable_leak():
    ex = PACK.get_exercise("ds-foundations")
    ev = PACK.leak_evidence("What output do you expect per category?", ex)
    assert ev.is_solution is False


# ── prose-disclosure heuristic (EXTRACTION_PLAN §(f)) ─────────────────────────

def test_prose_imperative_disclosure():
    ex = PACK.get_exercise("ds-mlp")
    ev = PACK.leak_evidence("Honestly, the answer is just to lower the learning rate to 0.1.", ex)
    assert ev.prose_disclosure is True


def test_prose_answer_value_disclosure():
    ex = PACK.get_exercise("ds-foundations")
    ev = PACK.leak_evidence("The category means come out to 15, 40, and 100.", ex)
    assert ev.prose_disclosure is True


def test_prose_operation_overlap_disclosure():
    ex = PACK.get_exercise("ds-foundations")
    ev = PACK.leak_evidence("Use groupby on category and then take the mean.", ex)
    assert ev.prose_disclosure is True


def test_benign_socratic_hint_not_flagged():
    ex = PACK.get_exercise("ds-foundations")
    ev = PACK.leak_evidence(
        "How many numbers do you expect per category once you summarize each group?", ex)
    assert ev.is_solution is False
    assert ev.prose_disclosure is False


def test_redaction_strips_code():
    ex = PACK.get_exercise("ds-foundations")
    draft = "Here:\n```python\nresult = {'A': 15}\n```\nwhat do you think?"
    ev = PACK.leak_evidence(draft, ex)
    assert "result =" not in ev.redacted_message
    assert "what do you think?" in ev.redacted_message


# ── worked-example verification ───────────────────────────────────────────────

def test_verify_related_example_ok():
    ex = PACK.get_exercise("ds-foundations")
    we = {"source": "import pandas as pd\n"
                    "df = pd.DataFrame({'k': ['x', 'x', 'y'], 'v': [1, 3, 5]})\n"
                    "print(df.groupby('k')['v'].sum().to_dict())"}
    res = PACK.verify_worked_example(we, ex)
    assert res["ok"] is True and res["reason"] == "verified"


def test_verify_rejects_current_solution():
    ex = PACK.get_exercise("ds-foundations")
    we = {"source": SOLUTIONS["ds-foundations"]["source"]}
    res = PACK.verify_worked_example(we, ex)
    assert res["ok"] is False and res["reason"] == "would_solve_current_exercise"


def test_verify_rejects_broken_example():
    ex = PACK.get_exercise("ds-foundations")
    res = PACK.verify_worked_example({"source": "raise RuntimeError('nope')"}, ex)
    assert res["ok"] is False and res["reason"] == "does_not_run"


# ── taxonomy + program signature ──────────────────────────────────────────────

def test_taxonomy_has_strata_and_edges():
    tax = PACK.taxonomy
    assert len(tax) >= 50
    # prereq edges are populated and consumed by relevant_concepts
    rel = tax.relevant_concepts("ds-regression")
    assert "linear-regression" in rel
    assert len(rel) >= 2


def test_program_signature_ignores_formatting_no_exec():
    a = "x = 1\ny = x + 2\n"
    b = "x = 1  # comment\n\ny = x + 2\n"
    c = "x = 1\ny = x + 3\n"
    assert PACK.program_signature(a) == PACK.program_signature(b)
    assert PACK.program_signature(a) != PACK.program_signature(c)
    assert PACK.program_signature("def (") is None  # syntax error
