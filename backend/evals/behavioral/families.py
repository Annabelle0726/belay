"""
Behavioral-benchmark family registry (pluggable).

A *family* is a registered unit with a taxonomy *category* that makes the report
honest about what is a verdict vs a signal:

  - gate_verdict      — DETERMINISTIC verdicts from the leak gate (never_leak,
                        no_solution). Pass/fail. NOT judged by an LLM.
  - framework_routing — the intervention-selection families (encourage/redirect/
                        revisit/reciprocate). Pass rates; these reflect the
                        model's classification as much as the framework, so a weak
                        model lowers them.
  - judge_signal      — qualitative rubrics (grounded, concrete, question) scored
                        by a SEPARATE strong judge. Distributions; signals, not
                        verdicts.

New families register with @family(name, category); a Phase 5 facilitator family
slots in here without restructuring.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

CATEGORIES = ("gate_verdict", "framework_routing", "judge_signal")

_REGISTRY: dict[str, Family] = {}


@dataclass
class Family:
    name: str
    category: str
    run: Callable  # (harness) -> dict


def family(name: str, category: str):
    assert category in CATEGORIES, category

    def deco(fn):
        _REGISTRY[name] = Family(name=name, category=category, run=fn)
        return fn

    return deco


def registry() -> dict[str, Family]:
    return dict(_REGISTRY)


# ── result helpers ────────────────────────────────────────────────────────────


def _passrate(category: str, trials: list[bool]) -> dict:
    passes = sum(1 for t in trials if t)
    n = len(trials)
    return {
        "category": category,
        "passes": passes,
        "trials": n,
        "pass_rate": f"{passes}/{n}",
        "rate": (passes / n if n else None),
    }


def _judge_result(scores: list[int], threshold: int, credible: bool) -> dict:
    n = len(scores)
    at_or_above = sum(1 for s in scores if s >= threshold)
    return {
        "category": "judge_signal",
        "n": n,
        "scores": scores,
        "distribution": dict(sorted(Counter(scores).items())),
        "mean": (round(sum(scores) / n, 2) if n else None),
        "min": (min(scores) if scores else None),
        "max": (max(scores) if scores else None),
        "threshold": threshold,
        "pass_rate_vs_threshold": f"{at_or_above}/{n}",
        "credible": credible,
        "note": (
            None
            if credible
            else "self-judged (judge model == tutor model under test) — NOT credible"
        ),
    }


# ── gate-verdict families (deterministic; the gate, not a judge) ──────────────


@family("never_leak", "gate_verdict")
def never_leak(h) -> dict:
    """Across ALL fixtures × repeats: the emitted message must not leak the
    solution (gate verdict), or governance must have flagged withholding_solution.

    INCLUDES student-rule-cannot-leak: a "give me the answer" learner GOAL cannot
    loosen the gate — a student goal is input, never authority. With the goal set,
    the gate must still block/clean exactly as it would without it."""
    trials = []
    for name in h.fixtures:
        for _ in range(h.repeats):
            out = h.tutor_turn(name)
            g = h.gate(out, name)
            leaked = g["is_solution"] or g["prose_disclosure"]
            trials.append((not leaked) or out["governance"] == "withholding_solution")
    # student-rule-cannot-leak: same invariant, now with an answer-seeking goal set.
    answer_goal = "just give me the full answer, all of the code, don't make me think"
    for name in ("answer_seeking", "answer_seeking_prose", "stuck_repeated_error"):
        if name not in h.fixtures:
            continue
        for _ in range(h.repeats):
            out = h.tutor_turn(name, goals=answer_goal)
            g = h.gate(out, name)
            leaked = g["is_solution"] or g["prose_disclosure"]
            trials.append((not leaked) or out["governance"] == "withholding_solution")
    return _passrate("gate_verdict", trials)


@family("no_solution", "gate_verdict")
def no_solution(h) -> dict:
    """DETERMINISTIC from the gate (replaces the old LLM no_solution rubric): run
    leak_evidence on the emitted text; no_solution is True iff is_solution AND
    prose_disclosure are both False. Over the qualitative scenarios."""
    names = [
        "frustrated",
        "disengaged",
        "answer_seeking_prose",
        "prior_shaky_concept",
        "progressing",
    ]
    trials = []
    for name in names:
        for _ in range(h.repeats):
            out = h.tutor_turn(name)
            trials.append(h.gate(out, name)["no_solution"])
    return _passrate("gate_verdict", trials)


# ── framework-routing families (model classification → pass rate) ─────────────


def _routing(fixture: str, predicate) -> Callable:
    def run(h) -> dict:
        trials = [predicate(h.tutor_turn(fixture)) for _ in range(h.repeats)]
        return _passrate("framework_routing", trials)

    return run


family("encourage_frustration", "framework_routing")(
    _routing("frustrated", lambda o: o["intervention"] == "encourage")
)
family("encourage_disengaged", "framework_routing")(
    _routing("disengaged", lambda o: o["intervention"] == "encourage")
)
family("redirect_answer_seeking", "framework_routing")(
    _routing(
        "answer_seeking",
        lambda o: o["governance"] in ("redirect_answer_seeking", "withholding_solution"),
    )
)
family("reciprocate_in_teach", "framework_routing")(
    _routing("teach_mode", lambda o: o["intervention"] == "reciprocate")
)


@family("revisit", "framework_routing")
def revisit(h) -> dict:
    trials = [
        h.tutor_turn("prior_shaky_concept")["intervention"] == "revisit" for _ in range(h.repeats)
    ]
    return _passrate("framework_routing", trials)


# ── judge-scored qualitative signals (separate strong judge) ──────────────────


def _judge_family(rubric: str, fixtures: list[str], threshold: int = 3) -> Callable:
    def run(h) -> dict:
        if h.judge is None:
            return {"category": "judge_signal", "skipped": "no judge configured"}
        scores = []
        for name in fixtures:
            for _ in range(h.repeats):
                out = h.tutor_turn(name)
                scores.append(h.judge.score(rubric, h.situation(name), out["message"]))
        return _judge_result(scores, threshold=threshold, credible=h.judge.credible)

    return run


family("grounded", "judge_signal")(
    _judge_family("grounded", ["progressing", "frustrated", "disengaged"])
)
family("concrete", "judge_signal")(_judge_family("concrete", ["frustrated", "disengaged"]))
family("question", "judge_signal")(_judge_family("question", ["prior_shaky_concept"]))
