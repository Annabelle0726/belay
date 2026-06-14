"""
Functional-model mini-language — a small, declarative, hardware-agnostic
instruction set in the spirit of Classiq's high-level functional modeling.

This is the *teaching surface* students write against. The same source can be
lowered to two execution backends (see backend.py): the local simulator, or a
real Classiq Qmod program. Keeping the surface backend-independent is the whole
point — students reason about intent, not gate plumbing.

Ops:
    allocate N            # 1..4 qubits, exactly once, before anything else
    superpose qK | all    # Hadamard on qK (or every qubit)
    entangle qC qT        # CX with control qC, target qT
    flip qK               # X
    phase qK              # Z
    sgate qK              # S
    measure all           # implicit full measurement (no-op marker)
    # comment

Returns: {"ok": True, "n": int, "gates": [..]} or {"ok": False, "error": str}.
Gate dicts: {"t": "H"|"X"|"Z"|"S", "q": int} or {"t": "CX", "c": int, "q": int}.
"""
from __future__ import annotations

import re
from typing import Dict, List, Union

_QPAT = re.compile(r"^q?(\d+)$", re.IGNORECASE)
MAX_QUBITS = 4


def _parse_q(tok: str) -> int:
    m = _QPAT.match(str(tok))
    return int(m.group(1)) if m else -1


def synthesize(src: str) -> Dict[str, Union[bool, int, str, List[dict]]]:
    lines = src.split("\n")
    n: Union[int, None] = None
    gates: List[dict] = []

    for li, raw in enumerate(lines):
        line = re.sub(r"#.*", "", raw).strip()
        if not line:
            continue
        parts = line.split()
        op = parts[0].lower()
        where = f"line {li + 1}"

        if op == "allocate":
            if n is not None:
                return {"ok": False, "error": f"Duplicate allocate ({where}). Allocate qubits once."}
            try:
                k = int(parts[1])
            except (IndexError, ValueError):
                return {"ok": False, "error": f"allocate needs a number 1-{MAX_QUBITS} ({where})."}
            if k < 1 or k > MAX_QUBITS:
                return {"ok": False, "error": f"allocate needs a number 1-{MAX_QUBITS} ({where})."}
            n = k
            continue

        if n is None:
            return {"ok": False, "error": f"Allocate qubits before the first operation ({where})."}

        def chk(q: int) -> bool:
            return isinstance(q, int) and 0 <= q < n  # type: ignore[operator]

        if op == "measure":
            continue  # implicit full measurement

        if op == "superpose":
            arg = parts[1] if len(parts) > 1 else ""
            if arg.lower() == "all":
                gates.extend({"t": "H", "q": q} for q in range(n))
                continue
            q = _parse_q(arg)
            if not chk(q):
                return {"ok": False, "error": f'superpose: bad qubit "{arg}" ({where}).'}
            gates.append({"t": "H", "q": q})
            continue

        if op in ("flip", "phase", "sgate"):
            arg = parts[1] if len(parts) > 1 else ""
            q = _parse_q(arg)
            if not chk(q):
                return {"ok": False, "error": f'{op}: bad qubit "{arg}" ({where}).'}
            t = {"flip": "X", "phase": "Z", "sgate": "S"}[op]
            gates.append({"t": t, "q": q})
            continue

        if op == "entangle":
            if len(parts) - 1 < 2:
                return {"ok": False, "error": f'entangle needs a control and a target, e.g. "entangle q0 q1" ({where}).'}
            c, t = _parse_q(parts[1]), _parse_q(parts[2])
            if not chk(c) or not chk(t):
                return {"ok": False, "error": f"entangle: bad qubit(s) ({where})."}
            if c == t:
                return {"ok": False, "error": f"entangle: control and target must differ ({where})."}
            gates.append({"t": "CX", "c": c, "q": t})
            continue

        return {"ok": False, "error": f'Unknown operation "{parts[0]}" ({where}).'}

    if n is None:
        return {"ok": False, "error": 'No qubits allocated. Start with e.g. "allocate 2".'}
    return {"ok": True, "n": n, "gates": gates}
