"""
State-vector simulator — a faithful Python port of the artifact's JS core.

Convention (must match the front-end and the grader):
    qubit 0 == leftmost / most-significant bit of the basis-state index.
    mask(q, n) = 1 << (n - 1 - q)

Kept deliberately dependency-free (stdlib `complex` only) so the whole
quantum layer is testable without installing anything, and so it can serve
as the offline / CI backend when the Classiq platform is not reachable.
"""
from __future__ import annotations

import cmath
import math
from typing import Dict, List

SQ = 1.0 / math.sqrt(2.0)

# 2x2 single-qubit gate matrices as nested tuples of complex.
GATES: Dict[str, tuple] = {
    "H": ((complex(SQ), complex(SQ)), (complex(SQ), complex(-SQ))),
    "X": ((complex(0), complex(1)), (complex(1), complex(0))),
    "Z": ((complex(1), complex(0)), (complex(0), complex(-1))),
    "S": ((complex(1), complex(0)), (complex(0), complex(0, 1))),
}


def mask_of(q: int, n: int) -> int:
    return 1 << (n - 1 - q)


def bit_of(i: int, q: int, n: int) -> int:
    return (i >> (n - 1 - q)) & 1


def bits_of(i: int, n: int) -> str:
    return "".join(str(bit_of(i, k, n)) for k in range(n))


def init_state(n: int) -> List[complex]:
    s = [complex(0) for _ in range(1 << n)]
    s[0] = complex(1)
    return s


def apply_single(state: List[complex], n: int, q: int, u: tuple) -> List[complex]:
    m = mask_of(q, n)
    out = list(state)
    for i in range(len(state)):
        if (i & m) == 0:
            j = i | m
            a, b = state[i], state[j]
            out[i] = u[0][0] * a + u[0][1] * b
            out[j] = u[1][0] * a + u[1][1] * b
    return out


def apply_cx(state: List[complex], n: int, ctrl: int, tgt: int) -> List[complex]:
    mc, mt = mask_of(ctrl, n), mask_of(tgt, n)
    out = [None] * len(state)
    for i in range(len(state)):
        out[i] = state[i ^ mt] if (i & mc) else state[i]
    return out  # type: ignore[return-value]


def run_gates(gates: List[dict], n: int) -> List[complex]:
    """Apply a synthesized gate list to |0...0> and return the final state vector."""
    st = init_state(n)
    for g in gates:
        if g["t"] == "CX":
            st = apply_cx(st, n, g["c"], g["q"])
        else:
            st = apply_single(st, n, g["q"], GATES[g["t"]])
    return st


def distribution(state: List[complex], n: int, eps: float = 1e-6) -> Dict[str, float]:
    """Measurement-outcome probability mass keyed by bitstring."""
    probs: Dict[str, float] = {}
    for i, amp in enumerate(state):
        p = abs(amp) ** 2
        if p > eps:
            key = bits_of(i, n)
            probs[key] = probs.get(key, 0.0) + p
    return probs
