"""
Self-verifying worked-example checker.

Pure, deterministic, no LLM, no network.  Called by the orchestrator after the
reasoner produces a `worked_example` dict for a `worked_analogy` turn.

Verification passes iff ALL of:
  1. The source COMPILES  (synthesize returns ok=True).
  2. The source does NOT meet the current exercise goal  (reuses is_goal_meeting
     from quantum/leak_check.py so the verdict is provably identical to governance's
     withholding_solution gate — a verified example can never be a solution leak).
  3. IF expected_dist is provided: the simulated distribution matches within tol.

Return shape:
  {"ok": bool, "reason": str, "dist": dict|None, "claim_ok": bool|None}
  ok=True  → "verified"
  ok=False → reason ∈ {"does_not_compile", "would_solve_current_exercise",
                        "prediction_mismatch"}
  claim_ok → True/False if expected_dist was given and matches/mismatches;
             None if no expected_dist was provided.
"""
from __future__ import annotations

from typing import Dict, Optional

from .functional_model import synthesize
from .leak_check import is_goal_meeting
from .simulator import distribution, run_gates


def verify_worked_example(
    we: dict,
    target: Dict[str, float],
    tol: float,
    sim=None,
) -> dict:
    """Verify that a worked-example snippet is sound for showing to the student.

    Parameters
    ----------
    we       : dict with keys "source" (required) and "expected_dist" (optional).
    target   : the current exercise's target distribution.
    tol      : the current exercise's goal tolerance (typically 0.07).
    sim      : a QuantumBackend instance; defaults to a fresh LocalSimulator.
    """
    source: str = (we.get("source") or "").strip()
    expected: Optional[Dict[str, float]] = we.get("expected_dist")

    # ── 1. Must compile ───────────────────────────────────────────────────────
    synth = synthesize(source)
    if not synth.get("ok"):
        return {"ok": False, "reason": "does_not_compile", "dist": None,
                "claim_ok": None}

    # ── 2. Run the circuit ────────────────────────────────────────────────────
    from .backend import LocalSimulator
    _sim = sim or LocalSimulator()
    raw_dist = distribution(run_gates(synth["gates"], synth["n"]), synth["n"])

    # ── 3. Must NOT solve the current exercise ────────────────────────────────
    # is_goal_meeting wraps the same grader governance uses, so this check is
    # provably consistent with withholding_solution.  A verified example is
    # non-leaking by construction; governance's LAST gate will still run and
    # could independently block anything that slipped through, but it never
    # will because we already excluded goal-meeting snippets here.
    if is_goal_meeting(source, target, tol, _sim):
        return {"ok": False, "reason": "would_solve_current_exercise",
                "dist": raw_dist, "claim_ok": None}

    # ── 4. Optional: predicted distribution must match within tol ─────────────
    claim_ok: Optional[bool] = None
    if expected is not None:
        keys = set(expected) | set(raw_dist)
        tvd = 0.5 * sum(abs(expected.get(b, 0.0) - raw_dist.get(b, 0.0))
                        for b in keys)
        claim_ok = tvd <= tol
        if not claim_ok:
            return {"ok": False, "reason": "prediction_mismatch",
                    "dist": raw_dist, "claim_ok": False}

    return {"ok": True, "reason": "verified", "dist": raw_dist,
            "claim_ok": claim_ok}
