"""
Classiq execution backend.

Lowers the same gate list the LocalSimulator runs into a Qmod model, sends it
to the Classiq synthesis engine, and executes the resulting quantum program,
then folds sampled shot counts into the outcome-probability dict the grader
expects.

This is the production path: it replaces the in-artifact stand-in with the
partner's actual platform (Classiq SDK + synthesis + execution), which is what
the proposal commits to.

-----------------------------------------------------------------------------
INTEGRATION NOTES — verify against your pinned Classiq SDK version (~0.86):
  * Auth: run `classiq.authenticate()` once interactively, or set the Classiq
    credentials in the environment for headless/server use. We do NOT bundle
    credentials here.
  * API shape used below (synthesize(main) -> qprog; ExecutionSession(qprog)
    .sample() -> result with parsed counts) matches current docs, but exact
    method/attribute names have shifted across minor versions — this module is
    isolated precisely so a one-file update tracks SDK drift.
  * ENDIANNESS: Classiq's reported bitstrings may be ordered opposite to our
    convention (qubit 0 = leftmost). `REVERSE_BITS` reconciles it; confirm with
    a Bell-pair smoke test (02 · Entanglement) the first time you wire a live
    backend, and flip if 01/10 leak in where 00/11 are expected.
-----------------------------------------------------------------------------
"""
from __future__ import annotations

from typing import Dict, List

DEFAULT_SHOTS = 4096
REVERSE_BITS = True  # see ENDIANNESS note above


def _build_main(gates: List[dict], n: int):
    """Construct a Qmod `main` that records the gate list. Imports are local so
    the rest of the app runs without the classiq package installed."""
    from classiq import (  # type: ignore
        CX,
        H,
        Output,
        QArray,
        QBit,
        S,
        X,
        Z,
        allocate,
        qfunc,
    )

    op = {"H": H, "X": X, "Z": Z, "S": S}

    @qfunc
    def main(q: Output[QArray[QBit]]):  # type: ignore[valid-type]
        allocate(n, q)
        for g in gates:
            if g["t"] == "CX":
                CX(q[g["c"]], q[g["q"]])
            else:
                op[g["t"]](q[g["q"]])

    return main


def _counts_to_probs(counts: Dict[str, int], n: int) -> Dict[str, float]:
    total = sum(counts.values()) or 1
    probs: Dict[str, float] = {}
    for bits, c in counts.items():
        key = bits[::-1] if REVERSE_BITS else bits
        key = key.zfill(n)[:n]
        probs[key] = probs.get(key, 0.0) + c / total
    return probs


class ClassiqBackend:
    name = "classiq"

    def __init__(self, shots: int = DEFAULT_SHOTS):
        self.shots = shots

    def probabilities(self, gates: List[dict], n: int) -> Dict[str, float]:
        from classiq import synthesize  # type: ignore
        from classiq.execution import ExecutionSession  # type: ignore

        main = _build_main(gates, n)
        qprog = synthesize(main)
        with ExecutionSession(qprog) as session:
            result = session.sample()  # ExecutionDetails

        # Normalize across SDK result shapes into a {bitstring: count} dict.
        counts = getattr(result, "counts", None)
        if counts is None:
            parsed = getattr(result, "parsed_counts", None)
            if parsed is not None:
                counts = {
                    "".join(str(b) for b in getattr(s, "state", {}).values()): s.shots
                    for s in parsed
                }
        if not counts:
            raise RuntimeError(
                "Classiq execution returned no counts; check SDK version and the "
                "result-parsing branch in classiq_backend.py."
            )
        return _counts_to_probs(dict(counts), n)
