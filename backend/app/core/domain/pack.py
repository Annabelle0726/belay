"""
The core domain seam: `DomainPack` and `KnowledgeBase` protocols.

A `DomainPack` is everything the domain-agnostic agent loop, governance,
measures, and learner model need in order to teach a specific subject without
importing that subject's concrete modules. The active pack is chosen at runtime
by the registry (see `registry.get_active_pack`).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .types import (
    Exercise,
    LeakEvidence,
    Module,
    Passage,
    PersonaSpec,
    RunResult,
    Taxonomy,
    VerifyResult,
    WorkedExample,
)


@runtime_checkable
class MisconceptionLibrary(Protocol):
    """Per-exercise misconception / expectation map (EMT dialogue input).

    ``for_exercise`` returns the expectations + likely misconceptions (each with
    an observable signature and a Socratic peer move) for an exercise, merged with
    any cross-cutting items. Shape matches the dict the Peer-Reasoner context
    already consumes.
    """

    def for_exercise(self, exercise_id: str) -> dict:
        ...


@runtime_checkable
class KnowledgeBase(Protocol):
    """Retrieval seam for a pack's grounded source material.

    LOAD-BEARING GOVERNANCE CONTRACT: governance treats exercise solutions as
    leak-gated regardless of whether they arrive via generation or retrieval. A
    passage surfaced by ``search`` is subject to the same deterministic leak gate
    as a model-generated draft; retrieving the answer is not a loophole around
    "never hand over the solution". This is the reason this seam exists and is
    declared now, even though no retrieval is implemented yet — it fixes the
    contract a future retrieval-backed pack must honor.

    ``search`` returns passages each carrying text, a source citation, and a
    locator, so any disclosure can be cited and traced.
    """

    def search(self, query: str, k: int) -> list[Passage]:
        ...


@runtime_checkable
class DomainPack(Protocol):
    """A pluggable teaching domain.

    Core components depend on this interface, never on a concrete domain module.
    The quantum pack is the first implementation; a data-science pack follows in
    Phase 1b.
    """

    # -- identity & persona ----------------------------------------------------
    id: str
    persona: PersonaSpec
    taxonomy: Taxonomy            # a Sequence[Concept] with lookup edges

    # -- curriculum ------------------------------------------------------------
    def curriculum(self) -> Sequence[Module]:
        """The pack's modules + exercises (the GET /api/curriculum payload)."""
        ...

    def get_exercise(self, exercise_id: str) -> Exercise:
        """Look up a single exercise by id (raises KeyError if unknown)."""
        ...

    # -- runner (compile + execute + grade) ------------------------------------
    def run(self, source: str, exercise: Exercise) -> RunResult:
        """Compile, execute, and grade a submission against the exercise goal,
        returning the pack-agnostic `RunResult` envelope. Student code MUST be
        executed through `core/runner`, never in the main process."""
        ...

    def program_signature(self, source: str):
        """A structural fingerprint of ``source`` for the §5 nontrivial-revision
        measure, computed WITHOUT executing the code (parse/compile only). Two
        sources that differ only in whitespace/comments must compare equal;
        meaningfully different programs must compare unequal. Return None when the
        source does not parse."""
        ...

    # -- worked-example verification ------------------------------------------
    def verify_worked_example(
        self, worked_example: WorkedExample, exercise: Exercise
    ) -> VerifyResult:
        """Deterministically verify a worked example is sound to show: it compiles,
        does NOT solve the current exercise, and (if a prediction is given) matches.

        Note: takes the current ``exercise`` (target/tol) in addition to the
        worked example, because the non-leak and prediction checks are defined
        relative to the exercise being worked.
        """
        ...

    # -- misconceptions --------------------------------------------------------
    def misconceptions(self) -> MisconceptionLibrary:
        """The pack's misconception/expectation library."""
        ...

    # -- governance evidence ---------------------------------------------------
    def leak_evidence(self, draft: str, exercise: Exercise) -> LeakEvidence:
        """Evidence for the core governance leak gate: whether ``draft`` contains a
        goal-meeting solution for ``exercise``, plus a redaction of the draft with
        any solution surface stripped. The block/rewrite decision is core's; this
        only supplies evidence."""
        ...

    # -- knowledge (retrieval seam; may be absent) -----------------------------
    def knowledge(self) -> KnowledgeBase | None:
        """The pack's knowledge base, or None if it has no retrieval surface."""
        ...
