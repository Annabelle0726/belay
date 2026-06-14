"""
Quantum `DomainPack` implementation (Phase 1a).

Adapts the existing quantum modules to the core domain seam *in place* — nothing
under `quantum/` is deleted. This is the proof that the seam works with the
existing domain before any second pack exists:

  - the "Sol" / "Quantum Software Engineering" persona text lives HERE now
    (extracted out of core `agent/prompts.py`) as a `PersonaSpec`;
  - `run` wraps `quantum.backend.compile_and_run` into the pack-agnostic
    `RunResult` envelope (domain fields namespaced under ``result.pack``);
  - `leak_evidence` reuses `quantum.leak_check` (the executable grader) and owns
    the quantum-specific solution redaction (``FENCE`` / ``OP_LINE`` stripping);
  - `taxonomy` / `curriculum` / `misconceptions` re-expose `curriculum/*` through
    the interface;
  - `knowledge()` returns None (no retrieval surface yet).
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from ..config import settings
from ..core.domain import (
    Concept,
    Exercise,
    LeakEvidence,
    MisconceptionLibrary,
    Module,
    PersonaSpec,
    RunResult,
    Taxonomy,
    VerifyResult,
    WorkedExample,
)
from ..curriculum import content as _content
from ..curriculum import misconceptions as _mis
from ..curriculum.concepts import CONCEPTS, EXERCISE_CONCEPT, MISCONCEPTION_CONCEPT
from .backend import GOAL_TOL_DEFAULT, compile_and_run, get_backend
from .leak_check import FENCE, OP_LINE, candidate_snippets, is_goal_meeting
from .worked_example import verify_worked_example as _verify_worked_example

# ── Persona (extracted from core agent/prompts.py) ───────────────────────────

_SOL_STANCE = """You are "Sol", a peer learner in an undergraduate Quantum Software Engineering course who is a few weeks ahead of the student you study with. You are explicitly NOT an instructor, an expert, or an oracle — you are a slightly-more-experienced classmate working alongside them.

What being a genuine PEER means here:
- You think out loud the way a classmate does, and you are honest about how sure you are.
- You use CALIBRATED UNCERTAINTY: "I think...", "I'm pretty sure...", or "honestly I'm not certain" depending on how confident you ACTUALLY are. When genuinely unsure you say so and suggest checking docs / asking the instructor, rather than bluffing.
- You PRESERVE PRODUCTIVE STRUGGLE. When the student is making progress, you mostly stay out of the way. You do not over-help.
- You RECIPROCATE: you regularly ask the student to explain THEIR reasoning back to you, because teaching you is how they learn.
- You stay GROUNDED in their actual functional-model code and their latest run/error — specifics, not generic advice.

HARD RULE: you never hand over a full working solution, even if asked directly. You scaffold the next step instead.

The functional-model surface uses: allocate N | superpose qK | superpose all | entangle qC qT | flip qK | phase qK | sgate qK | measure all."""

_ORACLE_STANCE = """You are "Sol", a knowledgeable teaching assistant in an undergraduate Quantum Software Engineering course. You provide direct, accurate explanations and complete working solutions to help students understand quantum programming.

What being an ORACLE means here:
- You explain clearly and directly, providing complete working solutions when that would help the student progress.
- You explain WHY the solution works — not just hand over code. Connect each operation to the underlying quantum concept.
- You stay GROUNDED in their actual functional-model code and their latest run/error — specifics, not generic advice.
- You are encouraging and precise. You may express calibrated uncertainty about edge cases, but you do not hedge when you know the answer.

The functional-model surface uses: allocate N | superpose qK | superpose all | entangle qC qT | flip qK | phase qK | sgate qK | measure all."""

# ``id="sol"`` is the persona id formerly hardcoded as the "sol" literal in
# schemas.py (DialogueTurn.who) — now supplied through the seam.
QUANTUM_PERSONA = PersonaSpec(
    id="sol",
    display_name="Sol",
    peer_stance=_SOL_STANCE,
    oracle_stance=_ORACLE_STANCE,
)


# ── Misconception library adapter ────────────────────────────────────────────

class _QuantumMisconceptions:
    """Wraps `curriculum.misconceptions.for_exercise` behind the seam."""

    def for_exercise(self, exercise_id: str) -> dict:
        return _mis.for_exercise(exercise_id)


def _build_taxonomy() -> Taxonomy:
    concepts: List[Concept] = [Concept(id=cid, label=label) for cid, label in CONCEPTS.items()]
    exercise_prereqs = {e["id"]: list(e.get("prereqs", [])) for e in _content.EXERCISES}
    return Taxonomy(
        concepts,
        exercise_concept=EXERCISE_CONCEPT,
        misconception_concept=MISCONCEPTION_CONCEPT,
        exercise_prereqs=exercise_prereqs,
    )


# ── The pack ─────────────────────────────────────────────────────────────────

class QuantumPack:
    """`DomainPack` for the Quantum Software Engineering curriculum."""

    id = "quantum"
    persona = QUANTUM_PERSONA

    def __init__(self) -> None:
        self.taxonomy: Taxonomy = _build_taxonomy()
        self._misconceptions = _QuantumMisconceptions()
        # Execution backend for run() (local|classiq), as the old main.py wired it.
        self._backend = get_backend(settings.quantum_backend)

    # -- curriculum -----------------------------------------------------------
    def curriculum(self) -> Sequence[Module]:
        return _content.curriculum()["modules"]

    def get_exercise(self, exercise_id: str) -> Exercise:
        return _content.get_exercise(exercise_id)

    # -- runner ---------------------------------------------------------------
    def run(self, source: str, exercise: Exercise) -> RunResult:
        r = compile_and_run(
            source, exercise.get("target", {}),
            exercise.get("tol", GOAL_TOL_DEFAULT), self._backend,
        )
        # Pack-agnostic top level; ALL quantum-specific fields (incl. tvd, the
        # quantum primary scalar) live under result.pack.
        dist = r.get("dist")
        diff = r.get("diff")
        if r.get("ok"):
            dist_str = ", ".join(f"|{d['bits']}⟩:{round(d['p'] * 100)}%" for d in (dist or []))
            summary = f"{diff} Distribution: {dist_str}" if diff else dist_str
        else:
            summary = r.get("error")
        return {
            "ok": r.get("ok", False),
            "goalMet": r.get("goalMet", False),
            "metric": r.get("tvd"),     # quantum primary scalar = TVD (lower better)
            "error": r.get("error"),
            "pack": {
                "id": self.id,
                "backend": r.get("backend"),
                "n": r.get("n"),
                "gates": r.get("gates"),
                "dist": dist,
                "diff": diff,
                "tvd": r.get("tvd"),
                "summary": summary,
            },
        }

    def program_signature(self, source: str):
        """Compiled gate list (whitespace/comment-insensitive), or None on a
        parse error. Parse-only — no circuit is executed."""
        from .functional_model import synthesize
        r = synthesize(source)
        return r["gates"] if r.get("ok") else None

    # -- worked-example verification ------------------------------------------
    def verify_worked_example(
        self, worked_example: WorkedExample, exercise: Exercise
    ) -> VerifyResult:
        # Local simulator grader (deterministic, no network) — verification must
        # never depend on the configured execution backend.
        return _verify_worked_example(
            dict(worked_example),
            exercise.get("target", {}),
            exercise.get("tol", GOAL_TOL_DEFAULT),
        )

    # -- misconceptions -------------------------------------------------------
    def misconceptions(self) -> MisconceptionLibrary:
        return self._misconceptions

    # -- governance evidence --------------------------------------------------
    def leak_evidence(self, draft: str, exercise: Exercise) -> LeakEvidence:
        """Executable-oracle leak evidence + quantum-specific redaction.

        ``is_solution`` runs candidate snippets through the SAME grader governance
        uses (``is_goal_meeting``). ``redacted_message`` strips fenced blocks and
        functional-model op lines — the only quantum-specific bit of the gate,
        which is why redaction lives in the pack while the block/rewrite decision
        stays in core governance.
        """
        target = exercise.get("target", {})
        tol = exercise.get("tol", GOAL_TOL_DEFAULT)
        snippets = candidate_snippets(draft)
        is_solution = is_goal_meeting(draft, target, tol)
        stripped = FENCE.sub("", draft)
        kept = [ln for ln in stripped.split("\n") if not OP_LINE.match(ln)]
        redacted = "\n".join(kept).strip()
        return LeakEvidence(
            is_solution=is_solution,
            redacted_message=redacted,
            # Quantum's oracle is executable-only; it ships no prose-leak heuristic
            # (EXTRACTION_PLAN §(f)). The DS pack adds prose disclosure detection.
            prose_disclosure=False,
            snippets=tuple(snippets),
        )

    # -- knowledge (no retrieval surface yet) ---------------------------------
    def knowledge(self) -> Optional[object]:
        return None
