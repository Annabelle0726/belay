"""
Quantum execution boundary.

`QuantumBackend` is the seam between the teaching surface and *where the
circuit actually runs*. Two implementations:

    LocalSimulator   - exact state-vector probabilities (this module). No deps,
                       no network, no auth. Used for dev/CI and as the offline
                       fallback.
    ClassiqBackend   - real synthesis + execution on the Classiq platform
                       (classiq_backend.py). Used in the piloted system.

Both return an outcome-probability dict keyed by bitstring, so everything
downstream (the grader, the tutor context) is backend-agnostic.

`compile_and_run` reproduces the artifact's run() contract exactly, so the
existing front-end consumes the backend response unchanged.
"""
from __future__ import annotations

from typing import Dict, List, Protocol

from .functional_model import synthesize
from .simulator import distribution, run_gates

GOAL_TOL_DEFAULT = 0.07


class QuantumBackend(Protocol):
    name: str

    def probabilities(self, gates: List[dict], n: int) -> Dict[str, float]:
        """Outcome probabilities keyed by bitstring (qubit 0 = leftmost)."""
        ...


class LocalSimulator:
    name = "local-statevector"

    def probabilities(self, gates: List[dict], n: int) -> Dict[str, float]:
        return distribution(run_gates(gates, n), n)


def goal_check(probs: Dict[str, float], target: Dict[str, float], tol: float):
    """TVD-based comparison. Returns (goal_met, diff_text, tvd, dist_list)."""
    keys = set(target) | set(probs)
    unexpected, missing = [], []
    tvd = 0.0
    for b in keys:
        a = probs.get(b, 0.0)
        t = target.get(b, 0.0)
        tvd += abs(a - t)
        if a - t > tol:
            unexpected.append(b)
        elif t - a > tol:
            missing.append(b)
    tvd /= 2.0

    dist = sorted(
        ({"bits": b, "p": p} for b, p in probs.items() if p > 1e-6),
        key=lambda d: d["bits"],
    )
    goal_met = not unexpected and not missing
    if goal_met:
        diff = "The outcome distribution matches the target."
    else:
        u = (
            f"weight on {', '.join('|' + b + '⟩' for b in sorted(unexpected))} that the target doesn't have"
            if unexpected else ""
        )
        if missing:
            lead = " and is missing" if unexpected else "missing"
            m = f"{lead} weight on {', '.join('|' + b + '⟩' for b in sorted(missing))}"
        else:
            m = ""
        diff = f"Your run has {u}{m}.".replace("has  and", "has").replace("has missing", "is missing")
    return goal_met, diff, tvd, dist


def compile_and_run(src: str, target: Dict[str, float], tol: float, backend: QuantumBackend) -> dict:
    """Lower a functional model and run it. Mirrors the artifact run() contract."""
    syn = synthesize(src)
    if not syn["ok"]:
        return {"ok": False, "error": syn["error"]}
    n, gates = syn["n"], syn["gates"]
    probs = backend.probabilities(gates, n)  # type: ignore[arg-type]
    goal_met, diff, tvd, dist = goal_check(probs, target, tol)
    return {
        "ok": True,
        "backend": backend.name,
        "n": n,
        "gates": gates,
        "dist": dist,
        "goalMet": goal_met,
        "diff": diff,
        "tvd": tvd,
    }


def get_backend(kind: str = "local") -> QuantumBackend:
    """Factory. `classiq` requires the classiq SDK + authentication."""
    if kind == "classiq":
        from .classiq_backend import ClassiqBackend  # lazy: only import if selected
        return ClassiqBackend()
    return LocalSimulator()
