"""
Curriculum content + structure.

Three stackable ~4-week modules (Foundations -> Intermediate -> Advanced),
matching the proposal's module design. Each exercise keeps the exact schema the
front-end and grader already use (target / tol / starter / prompt), so content
authored here renders in the artifact and grades on the backend without change.

The functional-model surface is intentionally low-floor / wide-walls /
high-ceiling (Resnick): a one-line first win, room to explore, and stretch
variants that scale the same idea up.
"""
from __future__ import annotations

from typing import Dict, List

EXERCISES: List[dict] = [
    # ---- Module 1 · Foundations -------------------------------------------
    {
        "id": "superpose",
        "module": "foundations",
        "order": 1,
        "prereqs": [],
        "title": "01 · Superposition",
        "concept": "single-qubit superposition",
        "goalText": "One qubit, equal odds of measuring 0 or 1 (50 / 50).",
        "target": {"0": 0.5, "1": 0.5},
        "tol": 0.07,
        "prompt": "Put a single qubit into an equal superposition — a 50/50 chance of 0 or 1 when measured.",
        "starter": "# Goal: one qubit in an equal superposition (50/50).\nallocate 1\n# your move here\nmeasure all\n",
    },
    {
        "id": "flip",
        "module": "foundations",
        "order": 2,
        "prereqs": ["superpose"],
        "title": "02 · Certainty",
        "concept": "deterministic state preparation (X gate)",
        "goalText": "One qubit measured as 1 with certainty (100%).",
        "target": {"1": 1.0},
        "tol": 0.07,
        "prompt": "Prepare a single qubit that is measured as 1 every single time. How is this different from superposition?",
        "starter": "# Goal: one qubit that always measures 1.\nallocate 1\n# your move here\nmeasure all\n",
    },
    # ---- Module 2 · Intermediate ------------------------------------------
    {
        "id": "bell",
        "module": "intermediate",
        "order": 1,
        "prereqs": ["superpose"],
        "title": "03 · Entanglement",
        "concept": "two-qubit entanglement (Bell pair)",
        "goalText": "Two qubits, perfectly correlated: only 00 and 11, each ~50%.",
        "target": {"00": 0.5, "11": 0.5},
        "tol": 0.07,
        "prompt": "Create a Bell pair: two qubits that always agree — 50% |00⟩ and 50% |11⟩, never |01⟩ or |10⟩.",
        "starter": "# Goal: a Bell pair on 2 qubits (00 and 11, 50/50).\nallocate 2\nsuperpose q0\n# what links q0 and q1 so they always agree?\nmeasure all\n",
    },
    {
        "id": "uniform2",
        "module": "intermediate",
        "order": 2,
        "prereqs": ["bell"],
        "title": "04 · Independence",
        "concept": "independent superposition vs. entanglement",
        "goalText": "Two qubits, all four outcomes equally likely (25% each).",
        "target": {"00": 0.25, "01": 0.25, "10": 0.25, "11": 0.25},
        "tol": 0.07,
        "prompt": "Make all four outcomes — 00, 01, 10, 11 — equally likely (25% each). Hint: this is NOT entanglement.",
        "starter": "# Goal: 00, 01, 10, 11 all equally likely (25% each).\n# This is the opposite of a Bell pair — think about each qubit on its own.\nallocate 2\n# your move here\nmeasure all\n",
    },
    # ---- Module 3 · Advanced ----------------------------------------------
    {
        "id": "ghz",
        "module": "advanced",
        "order": 1,
        "prereqs": ["bell"],
        "title": "05 · Scaling",
        "concept": "scaling entanglement to a 3-qubit GHZ state",
        "goalText": "Three qubits, all-0 or all-1 (50 / 50) — a GHZ state.",
        "target": {"000": 0.5, "111": 0.5},
        "tol": 0.07,
        "prompt": "Build a 3-qubit GHZ state: all three qubits agree — 50% |000⟩ and 50% |111⟩.",
        "starter": "# Goal: a 3-qubit GHZ state (000 and 111, 50/50).\nallocate 3\nsuperpose q0\n# spread the correlation from q0 out to q1 and q2\nmeasure all\n",
    },
    {
        "id": "phasekick",
        "module": "advanced",
        "order": 2,
        "prereqs": ["bell", "superpose"],
        "title": "06 · Phase is invisible to measurement",
        "concept": "relative phase does not change measurement statistics (Z after H)",
        "goalText": "Still 50/50 on one qubit — adding a phase changes the state but not these odds.",
        "target": {"0": 0.5, "1": 0.5},
        "tol": 0.07,
        "prompt": "Put a qubit in superposition, then apply a phase. Predict the measurement odds BEFORE you run. Why are they unchanged?",
        "starter": "# Goal: superpose, then add a phase. Predict before running.\nallocate 1\nsuperpose q0\n# add a phase on q0 — what do you expect to measure?\nmeasure all\n",
    },
]

MODULES: List[dict] = [
    {
        "id": "foundations",
        "title": "Module 1 · Foundations",
        "weeks": 4,
        "summary": "Qubits, superposition, and deterministic preparation. First wins in the functional-model surface.",
    },
    {
        "id": "intermediate",
        "title": "Module 2 · Intermediate",
        "weeks": 4,
        "summary": "Multi-qubit correlation: entanglement vs. independence — the course's central misconception, surfaced by contrast.",
    },
    {
        "id": "advanced",
        "title": "Module 3 · Advanced",
        "weeks": 4,
        "summary": "Scaling correlation (GHZ) and the role of phase. Stretch toward hybrid workflows on Classiq + ACCESS.",
    },
]

_BY_ID: Dict[str, dict] = {e["id"]: e for e in EXERCISES}


def get_exercise(exercise_id: str) -> dict:
    if exercise_id not in _BY_ID:
        raise KeyError(f"unknown exercise: {exercise_id}")
    return _BY_ID[exercise_id]


def curriculum() -> dict:
    by_module = {m["id"]: {**m, "exercises": []} for m in MODULES}
    for ex in sorted(EXERCISES, key=lambda e: (e["module"], e["order"])):
        by_module[ex["module"]]["exercises"].append(ex)
    return {"modules": [by_module[m["id"]] for m in MODULES]}
