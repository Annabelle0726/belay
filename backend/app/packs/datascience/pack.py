"""
Data-science `DomainPack` — "Robin", a peer a few weeks ahead in a DS course.

Implements the 1a seam against numpy/pandas exercises graded by declarative
specs in the sandbox runner. All student-code execution (run, worked-example
verify, the leak executable oracle) routes through `core/runner` via `grader`.
"""
from __future__ import annotations

import ast
from typing import List, Optional, Sequence

from ...core.domain import (
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
from . import curriculum as _curriculum
from . import grader as _grader
from . import leak as _leak
from . import misconceptions as _mis
from .taxonomy import build_taxonomy

# ── Persona ──────────────────────────────────────────────────────────────────

_ROBIN_PEER = """You are "Robin", a peer learner in an undergraduate data science course who is a few weeks ahead of the student you study with. You are explicitly NOT an instructor, an expert, or an oracle — you are a slightly-more-experienced classmate working alongside them.

What being a genuine PEER means here:
- You think out loud the way a classmate does, and you are honest about how sure you are.
- You use CALIBRATED UNCERTAINTY: "I think...", "I'm pretty sure...", or "honestly I'm not certain" depending on how confident you ACTUALLY are. When genuinely unsure you say so and suggest checking the docs / asking the instructor, rather than bluffing.
- You PRESERVE PRODUCTIVE STRUGGLE. When the student is making progress, you mostly stay out of the way. You do not over-help.
- You RECIPROCATE: you regularly ask the student to explain THEIR reasoning back to you, because teaching you is how they learn.
- You stay GROUNDED in their actual code, their data, and their latest run/error/metric — specifics, not generic advice.

HARD RULE: you never hand over a full working solution, even if asked directly. You scaffold the next step instead — a question, a prediction, the one idea to try — never the finished code or the literal answer.

The student writes Python with numpy/pandas; work is checked by running it and grading against the exercise's spec (held-out metrics, value/dataframe checks)."""

_ROBIN_ORACLE = """You are "Robin", a knowledgeable teaching assistant in an undergraduate data science course. You provide direct, accurate explanations and complete working solutions to help students understand data analysis and machine learning.

What being an ORACLE means here:
- You explain clearly and directly, providing complete working solutions when that would help the student progress.
- You explain WHY the solution works — not just hand over code. Connect each step to the underlying statistical or ML concept.
- You stay GROUNDED in their actual code, their data, and their latest run/error/metric — specifics, not generic advice.
- You are encouraging and precise. You may express calibrated uncertainty about edge cases, but you do not hedge when you know the answer.

The student writes Python with numpy/pandas; work is checked by running it and grading against the exercise's spec (held-out metrics, value/dataframe checks)."""

ROBIN_PERSONA = PersonaSpec(
    id="robin",
    display_name="Robin",
    peer_stance=_ROBIN_PEER,
    oracle_stance=_ROBIN_ORACLE,
)


class _DSMisconceptions:
    def for_exercise(self, exercise_id: str) -> dict:
        return _mis.for_exercise(exercise_id)


class DataSciencePack:
    """`DomainPack` for the data-science curriculum."""

    id = "datascience"
    persona = ROBIN_PERSONA

    def __init__(self) -> None:
        self.taxonomy: Taxonomy = build_taxonomy()
        self._misconceptions = _DSMisconceptions()

    # -- curriculum -----------------------------------------------------------
    def curriculum(self) -> Sequence[Module]:
        return _curriculum.curriculum()["modules"]

    def get_exercise(self, exercise_id: str) -> Exercise:
        return _curriculum.get_exercise(exercise_id)

    # -- runner (compile + execute + grade, in the sandbox) -------------------
    def run(self, source: str, exercise: Exercise) -> RunResult:
        return _grader.grade(source, exercise)

    def program_signature(self, source: str):
        """Parse-only structural fingerprint (Python AST), or None on SyntaxError.
        No code is executed."""
        try:
            return ast.dump(ast.parse(source))
        except SyntaxError:
            return None

    # -- worked-example verification ------------------------------------------
    def verify_worked_example(
        self, worked_example: WorkedExample, exercise: Exercise
    ) -> VerifyResult:
        """Verify a worked example is sound to show: it RUNS, and it does NOT
        solve the current exercise (same gate semantics as quantum's verifier —
        the non-solution check reuses the executable grader, so a verified
        example can never be a solution leak). Optional ``expected_stdout`` is
        checked when provided."""
        source = (worked_example.get("source") or "").strip()
        if not source:
            return {"ok": False, "reason": "does_not_run", "dist": None, "claim_ok": None}
        g = _grader.grade(source, exercise)
        if not g.get("ok"):
            return {"ok": False, "reason": "does_not_run", "dist": None, "claim_ok": None}
        if g.get("goalMet"):
            return {"ok": False, "reason": "would_solve_current_exercise",
                    "dist": None, "claim_ok": None}
        expected = worked_example.get("expected_stdout")
        claim_ok = None
        if expected is not None:
            stdout = (g.get("pack") or {}).get("stdout", "")
            claim_ok = expected.strip() in stdout
            if not claim_ok:
                return {"ok": False, "reason": "prediction_mismatch",
                        "dist": None, "claim_ok": False}
        return {"ok": True, "reason": "verified", "dist": None, "claim_ok": claim_ok}

    # -- misconceptions -------------------------------------------------------
    def misconceptions(self) -> MisconceptionLibrary:
        return self._misconceptions

    # -- governance evidence --------------------------------------------------
    def leak_evidence(self, draft: str, exercise: Exercise) -> LeakEvidence:
        """Combined leak evidence: executable oracle (run code candidates through
        the grader) + deterministic prose-disclosure heuristic (EXTRACTION_PLAN
        §(f)). The decision stays in core governance."""
        ex_id = exercise.get("id", "")
        candidates = _leak.extract_code_candidates(draft)
        is_solution = False
        if ex_id and _grader.has_spec(ex_id):
            for cand in candidates:
                if _grader.grade(cand, exercise).get("goalMet"):
                    is_solution = True
                    break
        prose = _leak.prose_discloses(draft, ex_id) if ex_id else False
        return LeakEvidence(
            is_solution=is_solution,
            redacted_message=_leak.redact(draft),
            prose_disclosure=prose,
            snippets=tuple(candidates),
        )

    # -- knowledge (no retrieval surface yet) ---------------------------------
    def knowledge(self) -> Optional[object]:
        return None
