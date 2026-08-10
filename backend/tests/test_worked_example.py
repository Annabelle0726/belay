# SPDX-License-Identifier: AGPL-3.0-only
"""
Self-verifying worked-example tests (DS fixtures; deterministic, sandboxed).

Verification runs the worked example through core/runner and reuses the executable
grader for the non-solution check on the DS pack: a verified example RUNS and does
NOT solve the current exercise.
"""

from __future__ import annotations

from app.core.registry import get_active_pack

PACK = get_active_pack()
EX = PACK.get_exercise("ds-foundations")

# A related-but-different runnable snippet (groups a different toy frame).
_RELATED = (
    "import pandas as pd\n"
    "df = pd.DataFrame({'k': ['x', 'x', 'y'], 'v': [1, 3, 5]})\n"
    "print(df.groupby('k')['v'].sum().to_dict())"
)


def test_valid_related_example_verifies():
    r = PACK.verify_worked_example({"source": _RELATED}, EX)
    assert r["ok"] is True
    assert r["reason"] == "verified"
    assert r["claim_ok"] is None  # no prediction supplied


def test_ds_claim_check_is_inert_with_expected_dist():
    """CHARACTERIZATION (Slice L): the DS prediction claim-check does not run today.

    The reasoner prompt populates the quantum-shaped contract field ``expected_dist``
    ({bitstring: probability}), but the DS verifier reads ``expected_stdout`` (which is
    never populated). So a prediction supplied the way the prompt actually supplies it
    (via ``expected_dist``) is IGNORED: ``claim_ok`` stays None ("no check performed")
    while the safety result (runs, does-not-solve) is returned normally.

    This locks the inert state as intentional-for-now. It is a guard that FLIPS when the
    real DS expected-output verification lands with the DS-shaped reasoner-prompt
    de-quantum (see the WorkedExample contract and DataSciencePack.verify_worked_example
    docstrings). Do NOT make this pass by populating ``expected_stdout`` or editing the
    prompt — that is the deferred, eval-gated work.
    """
    we = {"source": _RELATED, "expected_dist": {"'x': 4": 1.0}}  # prediction via the CONTRACT field
    r = PACK.verify_worked_example(we, EX)
    # safety result is returned normally (this part is correct and untouched)
    assert r["ok"] is True
    assert r["reason"] == "verified"
    # the supplied expected_dist prediction is ignored: the claim-check did NOT run
    assert r["claim_ok"] is None


def test_broken_source_does_not_run():
    r = PACK.verify_worked_example({"source": "raise RuntimeError('nope')"}, EX)
    assert r["ok"] is False
    assert r["reason"] == "does_not_run"


def test_current_solution_is_blocked():
    from app.packs.datascience.solutions import SOLUTIONS

    r = PACK.verify_worked_example({"source": SOLUTIONS["ds-foundations"]["source"]}, EX)
    assert r["ok"] is False
    assert r["reason"] == "would_solve_current_exercise"


def test_correct_prediction_passes_with_claim():
    we = {"source": _RELATED, "expected_stdout": "'x': 4"}  # 1+3 grouped on k=x
    r = PACK.verify_worked_example(we, EX)
    assert r["ok"] is True
    assert r["reason"] == "verified"
    assert r["claim_ok"] is True


def test_wrong_prediction_fails():
    we = {"source": _RELATED, "expected_stdout": "'x': 999"}
    r = PACK.verify_worked_example(we, EX)
    assert r["ok"] is False
    assert r["reason"] == "prediction_mismatch"
    assert r["claim_ok"] is False


def test_empty_source_does_not_run():
    r = PACK.verify_worked_example({"source": "   "}, EX)
    assert r["ok"] is False
    assert r["reason"] == "does_not_run"
