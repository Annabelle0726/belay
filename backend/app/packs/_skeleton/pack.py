# SPDX-License-Identifier: AGPL-3.0-only
"""
Minimal echo pack — a dependency-free `DomainPack` for core-only tests.

It implements the seam with trivial behavior (no student-code execution, no third
-party deps) so the orchestrated loop, governance, learner model, and context can
be exercised without any concrete domain. Template for authoring new packs.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...core.domain import (
    Concept,
    Exercise,
    KnowledgeBase,
    LeakEvidence,
    MisconceptionLibrary,
    Module,
    PersonaSpec,
    RunResult,
    Taxonomy,
    VerifyResult,
    WorkedExample,
)

SKELETON_PERSONA = PersonaSpec(
    id="echo",
    display_name="Echo",
    peer_stance="You are Echo, a peer study partner. Scaffold; never hand over the full solution.",
    oracle_stance="You are Echo, a teaching assistant. Explain directly and completely.",
)

_EXERCISE: Exercise = {
    "id": "echo-1",
    "title": "01 · Echo",
    "concept": "echo concept",
    "goalText": "Print the word ok.",
    "prompt": "Print ok.",
    "starter": "print('...')\n",
    "prereqs": [],
}

_MODULE: Module = {"id": "echo-module", "title": "Module 1 · Echo", "exercises": [_EXERCISE]}


class _EchoMisconceptions:
    def for_exercise(self, exercise_id: str) -> dict:
        return {
            "concept": "echo concept",
            "expectations": ["print the expected token"],
            "misconceptions": [
                {
                    "id": "echo-mis",
                    "belief": "printing is optional",
                    "signature": "no output",
                    "peer_move": "ask what output is expected",
                }
            ],
        }


class SkeletonPack:
    """Trivial echo `DomainPack`."""

    id = "_skeleton"
    persona = SKELETON_PERSONA

    def __init__(self) -> None:
        self.taxonomy: Taxonomy = Taxonomy(
            [
                Concept(id="echo-concept", label="Echo concept", prereqs=("echo-prereq",)),
                Concept(id="echo-prereq", label="Echo prerequisite"),
            ],
            exercise_concept={"echo-1": "echo-concept"},
            misconception_concept={"echo-mis": "echo-concept"},
            exercise_prereqs={"echo-1": []},
        )
        self._mis = _EchoMisconceptions()

    def curriculum(self) -> Sequence[Module]:
        return [_MODULE]

    def get_exercise(self, exercise_id: str) -> Exercise:
        if exercise_id != "echo-1":
            raise KeyError(f"unknown exercise: {exercise_id}")
        return _EXERCISE

    def run(self, source: str, exercise: Exercise) -> RunResult:
        # Echo "grader": goal met iff the source mentions ok. No execution.
        goal = "ok" in source
        return {
            "ok": True,
            "goalMet": goal,
            "metric": None,
            "error": None,
            "pack": {"id": self.id, "summary": "echo: matched" if goal else "echo: no match"},
        }

    def program_signature(self, source: str):
        return source.strip()

    def verify_worked_example(
        self, worked_example: WorkedExample, exercise: Exercise
    ) -> VerifyResult:
        return {"ok": True, "reason": "verified", "dist": None, "claim_ok": None}

    def misconceptions(self) -> MisconceptionLibrary:
        return self._mis

    def leak_evidence(self, draft: str, exercise: Exercise) -> LeakEvidence:
        return LeakEvidence(
            is_solution=False, redacted_message=draft, prose_disclosure=False, snippets=()
        )

    def knowledge(self) -> KnowledgeBase | None:
        return None
