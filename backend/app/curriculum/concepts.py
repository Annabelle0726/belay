"""
Canonical concept taxonomy for the QSE curriculum.

Provides:
  CONCEPTS              — {concept_id: human_label}
  EXERCISE_CONCEPT      — {exercise_id: concept_id}
  MISCONCEPTION_CONCEPT — {misconception_id: concept_id}
  concept_for_exercise(eid)      -> str | None
  concept_for_misconception(mid) -> str | None
  relevant_concepts(eid)         -> frozenset[str]  (own concept + prereqs')
"""
from __future__ import annotations

from typing import FrozenSet, Optional

CONCEPTS: dict[str, str] = {
    "superposition": "Single-qubit superposition",
    "determinism":   "Deterministic state preparation (X gate)",
    "measurement":   "Quantum measurement and outcome distributions",
    "entanglement":  "Two-qubit entanglement (Bell pair)",
    "independence":  "Independent superposition vs. entanglement",
    "scaling":       "Scaling entanglement to larger registers (GHZ)",
    "phase":         "Relative phase and measurement statistics",
    "abstraction":   "Specification → synthesized algorithm (abstraction + debugging)",
}

# Primary concept each exercise builds toward.
EXERCISE_CONCEPT: dict[str, str] = {
    "superpose":  "superposition",
    "flip":       "determinism",
    "bell":       "entanglement",
    "uniform2":   "independence",
    "ghz":        "scaling",
    "phasekick":  "phase",
}

# Stable mapping from misconception id to the concept it belongs to.
MISCONCEPTION_CONCEPT: dict[str, str] = {
    "M1.1-classical-ignorance":        "superposition",
    "M1.2-halfway-value":              "superposition",
    "M1.3-double-superpose":           "superposition",
    "M1.4-measurement-cosmetic":       "measurement",
    "M2.1-superpose-both-is-entangle": "entanglement",
    "M2.2-entangle-is-copy":           "entanglement",
    "M2.3-order-irrelevant":           "entanglement",
    "M2.4-independent-measurement":    "entanglement",
    "M2.5-uniform-needs-entangle":     "independence",
    "M2.6-uniform-is-entangled":       "independence",
    "M2.7-ghz-superpose-all":          "scaling",
    "M2.8-ghz-disconnected-links":     "scaling",
    "M3.1-literal-gates":              "abstraction",
    "M3.2-random-edits":               "abstraction",
    "M3.3-looks-right":                "abstraction",
}


def concept_for_exercise(exercise_id: str) -> Optional[str]:
    return EXERCISE_CONCEPT.get(exercise_id)


def concept_for_misconception(misconception_id: str) -> Optional[str]:
    return MISCONCEPTION_CONCEPT.get(misconception_id)


def relevant_concepts(exercise_id: str) -> FrozenSet[str]:
    """Concept ids relevant to an exercise: its own primary concept + all prereqs'.

    Uses content.py's prereq graph so the set widens as exercises stack on each other.
    """
    from .content import _BY_ID
    cids: set[str] = set()
    own = EXERCISE_CONCEPT.get(exercise_id)
    if own:
        cids.add(own)
    ex = _BY_ID.get(exercise_id)
    if ex:
        for prereq in ex.get("prereqs", []):
            pc = EXERCISE_CONCEPT.get(prereq)
            if pc:
                cids.add(pc)
    return frozenset(cids)
