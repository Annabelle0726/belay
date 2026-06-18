# SPDX-License-Identifier: Apache-2.0
"""
Supporting value types for the core domain seam.

These are the pack-agnostic data shapes the agent loop, governance, measures,
and the learner model exchange with a `DomainPack`. Dict-shaped payloads that
flow into the §6 trace (and therefore must JSON-serialize unchanged) are kept as
``TypedDict`` aliases over the existing dict shapes; value objects the core
passes around in-process are ``dataclass``es.

Pack-agnostic is the whole point: nothing here names a concrete domain (not data
science, not any specific subject). A concrete domain fills these in via its `DomainPack`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

# ── Persona ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PersonaSpec:
    """The injectable persona for the tutor.

    Replaces the formerly hardcoded ``SOL_STANCE`` / ``ORACLE_STANCE`` strings in
    core prompts. The pack supplies the stance text (including any domain surface
    description); core prompts are parameterized over this object so no persona or
    domain wording lives in the core.

    - ``id``           — the persona id (the old ``"sol"`` literal), supplied through the seam.
    - ``display_name`` — human name used in component prompts.
    - ``peer_stance``  — system-prompt stance text for the PEER condition.
    - ``oracle_stance``— system-prompt stance text for the ORACLE condition.
    """

    id: str
    display_name: str
    peer_stance: str
    oracle_stance: str


# ── Taxonomy ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Concept:
    """One concept in a domain's taxonomy.

    ``prereqs`` are prerequisite *concept* ids; the learner model's spaced-revisit
    machinery reads these edges through the `Taxonomy` interface.
    """

    id: str
    label: str
    prereqs: tuple[str, ...] = ()


class Taxonomy:
    """A ``Sequence[Concept]`` plus the lookup edges the persistent learner model
    and per-turn context need.

    Behaves as a sequence of `Concept` (so it satisfies the ``taxonomy:
    Sequence[Concept]`` member of `DomainPack`) while also exposing the
    exercise→concept, misconception→concept, and exercise-prerequisite edges that
    ``learner_model.due_review`` / ``update_concepts`` and ``context`` consume —
    all through this interface rather than by importing a concrete taxonomy module.
    """

    def __init__(
        self,
        concepts: Sequence[Concept],
        *,
        exercise_concept: Mapping[str, str],
        misconception_concept: Mapping[str, str],
        exercise_prereqs: Mapping[str, Sequence[str]],
    ) -> None:
        self._concepts: list[Concept] = list(concepts)
        self._by_id: dict[str, Concept] = {c.id: c for c in self._concepts}
        self._exercise_concept: dict[str, str] = dict(exercise_concept)
        self._misconception_concept: dict[str, str] = dict(misconception_concept)
        self._exercise_prereqs: dict[str, list[str]] = {
            k: list(v) for k, v in exercise_prereqs.items()
        }

    # -- Sequence[Concept] protocol -------------------------------------------
    def __iter__(self):
        return iter(self._concepts)

    def __len__(self) -> int:
        return len(self._concepts)

    def __getitem__(self, i):
        return self._concepts[i]

    # -- lookups (taxonomy edges) ---------------------------------------------
    @property
    def labels(self) -> dict[str, str]:
        """{concept_id: human_label} — the former ``CONCEPTS`` map."""
        return {c.id: c.label for c in self._concepts}

    def label(self, concept_id: str) -> str:
        c = self._by_id.get(concept_id)
        return c.label if c else concept_id

    def concept_for_exercise(self, exercise_id: str) -> str | None:
        return self._exercise_concept.get(exercise_id)

    def concept_for_misconception(self, misconception_id: str) -> str | None:
        return self._misconception_concept.get(misconception_id)

    def relevant_concepts(self, exercise_id: str) -> frozenset[str]:
        """Concept ids relevant to an exercise, for spaced revisit:
        - the exercise's own concept,
        - that concept's direct prerequisite concepts (Concept.prereqs edges),
        - and the concepts of the exercise's prerequisite exercises.
        """
        cids: set[str] = set()
        own = self._exercise_concept.get(exercise_id)
        if own:
            cids.add(own)
            own_concept = self._by_id.get(own)
            if own_concept:
                cids.update(own_concept.prereqs)
        for prereq in self._exercise_prereqs.get(exercise_id, []):
            pc = self._exercise_concept.get(prereq)
            if pc:
                cids.add(pc)
        return frozenset(cids)


# ── Curriculum / exercises ───────────────────────────────────────────────────
# Exercises and modules flow through the system as plain dicts (HTTP payloads,
# trace rows). They are documented here as TypedDicts so the expected shape is
# explicit, while remaining ordinary dicts at runtime.


class Exercise(TypedDict, total=False):
    id: str
    title: str
    concept: str
    goalText: str
    prompt: str
    target: dict[str, float]  # grading target (pack-interpreted)
    tol: float  # goal tolerance
    starter: str
    prereqs: list[str]


class Module(TypedDict, total=False):
    id: str
    title: str
    exercises: list[Exercise]


# ── Run result (pack-agnostic envelope) ──────────────────────────────────────


class RunResult(TypedDict, total=False):
    """Result of compiling + executing + grading a submission.

    Pack-agnostic top level so the §6 trace schema is stable across packs:
      - ``ok``      — did it run / compile without error?
      - ``goalMet`` — did it meet the exercise goal? (primary progress signal)
      - ``metric``  — the pack's primary scalar for this exercise, or None. NOT
                      direction-normalized across packs (DS regression: held-out
                      score; DS MLP: final loss); it is a
                      display/telemetry slot, not a cross-pack-comparable number.
      - ``error``   — error string, or None.
      - ``pack``    — namespaced domain envelope: ``{"id": <pack id>, ...}``. ALL
                      domain-specific result data lives here (e.g. DS checks /
                      stdout). Packs SHOULD include a
                      human-readable ``summary`` for the tutor context.
    """

    ok: bool
    goalMet: bool
    metric: float | None
    error: str | None
    pack: dict[str, Any]  # {"id": <pack id>, ...domain-specific fields}


# ── Worked-example verification ──────────────────────────────────────────────


class WorkedExample(TypedDict, total=False):
    source: str
    expected_dist: dict[str, float] | None


class VerifyResult(TypedDict, total=False):
    ok: bool
    reason: str
    dist: dict[str, float] | None
    claim_ok: bool | None


# ── Governance leak evidence ─────────────────────────────────────────────────


@dataclass(frozen=True)
class LeakEvidence:
    """Pack-supplied evidence for the core governance leak gate.

    The deterministic block/rewrite decision lives in core governance and
    consumes this object; the pack only supplies *evidence*, never the decision.

    - ``is_solution``      — the executable-oracle verdict: does the draft contain a
                             snippet that independently meets the exercise goal?
    - ``redacted_message`` — the draft with solution snippets stripped (the domain
                             knows how to strip its own surface), which core
                             governance wraps with a peer-voiced redirect.
    - ``prose_disclosure`` — a deterministic signal that the draft's *prose*
                             (code stripped) discloses the solution: imperative
                             solution-giving patterns, or essential-token/answer
                             overlap with the known solution. Added because the
                             executable oracle catches code leaks but not a prose
                             disclosure of the answer (EXTRACTION_PLAN §(f)). Packs
                             without prose heuristics leave it False.
    - ``snippets``         — the candidate solution snippets found (for telemetry).

    Core governance blocks on ``is_solution OR prose_disclosure`` (combined with
    its own answer-seeking detector). Bias cautious: a false positive is a wasted
    rewrite; a false negative is a leak.
    """

    is_solution: bool
    redacted_message: str
    prose_disclosure: bool = False
    snippets: tuple[str, ...] = ()


# ── Knowledge base (seam only — no retrieval is built yet) ───────────────────


@dataclass(frozen=True)
class Passage:
    """A retrieved passage. Carries a stable id, text, a source citation, and a
    locator so a citation can be rendered and traced back to its source. The ``id``
    is what governance records when it drops a leaking passage (never the text)."""

    id: str  # stable passage id (used in the retrieval trace / drop records)
    text: str
    citation: str  # source citation (e.g. document title / id)
    locator: str  # where in the source (page / section / line span)
