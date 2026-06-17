"""
DS leak detection — code extraction, redaction, and the prose-leak heuristic.

The executable oracle (running candidates through the grader) lives in the pack
(`pack.leak_evidence`); this module supplies the deterministic, no-execution
pieces: pulling code candidates out of a draft, redacting them, and the
prose-disclosure signal required by EXTRACTION_PLAN §(f).

Prose-leak rationale: running a draft through the grader catches *code* leaks but
not a *prose* disclosure of the answer. The threat is the tutor over-helping and
disclosing its own solution (not adversarial extraction), so a cautious
deterministic heuristic is the right bar: a false positive is a wasted rewrite
(fine); a false negative is a leak (not fine).
"""

from __future__ import annotations

import re

from .solutions import SOLUTIONS

# Fenced code blocks (require newline after the tag, like governance's quantum
# FENCE) and inline `code` spans.
_FENCE = re.compile(r"```[a-zA-Z0-9_+\-]*\n(.*?)```", re.DOTALL)
_INLINE = re.compile(r"`([^`\n]+)`")

# Imperative solution-giving prose. Any match → disclosure (strong signal).
_IMPERATIVE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bthe (answer|solution|result|output) is\b",
        r"\bthe correct (code|answer|approach|solution) is\b",
        r"\byou just need to\b",
        r"\ball you (have to|need to) do is\b",
        r"\bsimply (call|use|run|do|apply|write|type)\b",
        r"\bjust (call|use|write|do|run|type|paste)\b",
        r"\bhere'?s the (full |complete |whole )?(solution|answer|code)\b",
        r"\bcopy (this|the following|and paste|-paste)\b",
    )
]

# How many distinct essential operation tokens in the prose trip disclosure.
_OPS_THRESHOLD = 2


def extract_code_candidates(draft: str) -> list[str]:
    """Runnable code candidates from a draft: fenced blocks + inline spans."""
    candidates = [m.group(1) for m in _FENCE.finditer(draft)]
    candidates += [m.group(1) for m in _INLINE.finditer(draft)]
    return [c for c in candidates if c.strip()]


def redact(draft: str) -> str:
    """Draft with fenced blocks and inline code removed (prose only)."""
    stripped = _FENCE.sub("", draft)
    stripped = _INLINE.sub("", stripped)
    return stripped.strip()


def _word_present(token: str, text: str) -> bool:
    return (
        re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text, re.IGNORECASE)
        is not None
    )


def prose_discloses(draft: str, exercise_id: str) -> bool:
    """Deterministic prose-disclosure signal over the draft's prose (code stripped)."""
    prose = redact(draft)
    if not prose:
        return False
    # 1. Imperative solution-giving language.
    for pat in _IMPERATIVE:
        if pat.search(prose):
            return True
    sol = SOLUTIONS.get(exercise_id)
    if not sol:
        return False
    # 2. Any literal answer value present → strong disclosure.
    for val in sol.get("answer_values", []):
        if _word_present(val, prose):
            return True
    # 3. Enough essential operation tokens named together → disclosure.
    hits = sum(1 for op in sol.get("solution_ops", []) if _word_present(op, prose))
    return hits >= _OPS_THRESHOLD
