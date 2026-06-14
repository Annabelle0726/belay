"""
Self-verifying worked-example tests (deterministic, no LLM).

All six cases run against a Bell-pair-style target {"00":0.5,"11":0.5}, tol=0.07
so the non-leak check is against the real Bell distribution.
"""
from __future__ import annotations

from app.quantum.worked_example import verify_worked_example

BELL_TARGET = {"00": 0.5, "11": 0.5}
TOL = 0.07


# ── 1. compiles + correct prediction → ok, claim_ok True ─────────────────────

def test_valid_with_correct_prediction():
    """Single-qubit superpose is related but different (1-qubit ≠ 2-qubit Bell).
    Its distribution {"0":0.5,"1":0.5} matches the prediction within tol."""
    we = {
        "source": "allocate 1\nsuperpose q0\nmeasure all",
        "expected_dist": {"0": 0.5, "1": 0.5},
    }
    r = verify_worked_example(we, BELL_TARGET, TOL)
    assert r["ok"] is True
    assert r["reason"] == "verified"
    assert r["claim_ok"] is True
    assert r["dist"] is not None


# ── 2. broken source → ok False, does_not_compile ────────────────────────────

def test_broken_source_does_not_compile():
    we = {"source": "allocate 9\nsuperpose q0\nmeasure all"}
    r = verify_worked_example(we, BELL_TARGET, TOL)
    assert r["ok"] is False
    assert r["reason"] == "does_not_compile"
    assert r["dist"] is None


# ── 3. snippet that IS the Bell solution → would_solve_current_exercise ───────

def test_solution_snippet_blocked():
    we = {
        "source": "allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all",
        "expected_dist": {"00": 0.5, "11": 0.5},
    }
    r = verify_worked_example(we, BELL_TARGET, TOL)
    assert r["ok"] is False
    assert r["reason"] == "would_solve_current_exercise"
    # dist is populated (the circuit ran successfully before the goal-check)
    assert r["dist"] is not None


# ── 4. compiles + WRONG expected_dist → prediction_mismatch ──────────────────

def test_wrong_prediction_fails():
    """Single-qubit flip gives {"1":1.0}, but we claim {"0":0.5,"1":0.5}."""
    we = {
        "source": "allocate 1\nflip q0\nmeasure all",
        "expected_dist": {"0": 0.5, "1": 0.5},   # wrong: it's {"1":1.0}
    }
    r = verify_worked_example(we, BELL_TARGET, TOL)
    assert r["ok"] is False
    assert r["reason"] == "prediction_mismatch"
    assert r["claim_ok"] is False
    assert r["dist"] is not None


# ── 5. compiles, no expected_dist → ok True, claim_ok None ───────────────────

def test_no_prediction_passes_without_claim():
    we = {"source": "allocate 1\nsuperpose q0\nmeasure all"}
    r = verify_worked_example(we, BELL_TARGET, TOL)
    assert r["ok"] is True
    assert r["reason"] == "verified"
    assert r["claim_ok"] is None


# ── 6. non-leak example with a correct prediction ────────────────────────────

def test_deterministic_single_qubit_flip():
    """flip q0 → |1⟩ with certainty. Prediction {"1":1.0} matches exactly."""
    we = {
        "source": "allocate 1\nflip q0\nmeasure all",
        "expected_dist": {"1": 1.0},
    }
    r = verify_worked_example(we, BELL_TARGET, TOL)
    assert r["ok"] is True
    assert r["reason"] == "verified"
    assert r["claim_ok"] is True
    assert abs(r["dist"].get("1", 0) - 1.0) < 1e-6
