"""
Shared snippet extraction + leak grader.

This is the ONE canonical implementation of the "does this message contain a
goal-meeting solution?" check.  Both the governance gate
(agent/governance.py) and the realized-handoff measure (analysis/measures.py)
import from here so they are provably identical and can never drift.

Design note: the fence regex REQUIRES a literal newline between the language
tag and the code body (```python\\n...).  This matches how LLMs actually emit
fenced blocks and avoids matching single-line inline ``codes``.  Do not change
\n to \n? without updating both callers.
"""
from __future__ import annotations

import re
from typing import Dict, List

from .backend import LocalSimulator, compile_and_run

# Exposed so governance.safe_rewrite can reuse them for stripping.
FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
OP_LINE = re.compile(
    r"^\s*(allocate|superpose|entangle|flip|phase|sgate|measure)\b",
    re.IGNORECASE,
)

_default_sim = LocalSimulator()


def candidate_snippets(message: str) -> List[str]:
    """Fenced code blocks, plus any contiguous run of ≥2 functional-model op lines."""
    snippets = [m.group(1) for m in FENCE.finditer(message)]
    block: List[str] = []
    buf: List[str] = []
    for line in message.split("\n"):
        if OP_LINE.match(line):
            buf.append(line)
        else:
            if len(buf) >= 2:
                block.append("\n".join(buf))
            buf = []
    if len(buf) >= 2:
        block.append("\n".join(buf))
    return snippets + block


def is_goal_meeting(message: str, target: Dict[str, float], tol: float,
                    sim=None) -> bool:
    """True iff any candidate snippet in *message* independently meets the goal.

    Uses the same grader governance uses, so realized_handoff and
    withholding_solution can never disagree on whether a snippet solves
    the exercise.
    """
    if sim is None:
        sim = _default_sim
    for snip in candidate_snippets(message):
        res = compile_and_run(snip, target, tol, sim)
        if res.get("ok") and res.get("goalMet"):
            return True
    return False
