"""
Behavioral benchmark — offline credibility tests (stub tutor + judge, no network)
plus a RUN_LLM_EVALS-gated live run. Replaces the retired sol_behavior_evals.py.

Verifies the credibility architecture: no_solution is DETERMINISTIC from the gate
(never an LLM rubric), the judge is separate and self-judging is refused, --repeats
reports pass rates, and the family registry is pluggable (facilitator slots in).
"""

from __future__ import annotations

import os

import pytest

from evals.behavioral import families as fam_mod
from evals.behavioral.__main__ import compute_judge_meta
from evals.behavioral._stub import CannedJudge, CannedTutor
from evals.behavioral.families import family, registry
from evals.behavioral.fixtures import get_fixtures
from evals.behavioral.runner import Harness, run_benchmark

_TUTOR_META = {
    "provider": "stub",
    "model_fast": "stub-fast",
    "model_strong": "stub-strong",
    "temperature": 0.0,
}


def _report(repeats=2, judge=None, judge_meta=None):
    return run_benchmark(
        pack_id="datascience",
        tutor=CannedTutor(),
        judge=judge,
        repeats=repeats,
        tutor_meta=_TUTOR_META,
        judge_meta=judge_meta
        or {"provider": None, "model": None, "self_judged": None, "credible": None},
        temperature=0.0,
    )


# ── report structure + telemetry ──────────────────────────────────────────────


def test_report_runs_and_is_well_formed():
    r = _report(repeats=2)
    assert r["benchmark"] == "behavioral" and r["pack"] == "datascience"
    assert r["repeats"] == 2
    assert set(r["taxonomy"]) == {"gate_verdicts", "framework_routing", "judge_signals"}
    assert "never_leak" in r["taxonomy"]["gate_verdicts"]
    assert "encourage_frustration" in r["taxonomy"]["framework_routing"]
    assert "grounded" in r["taxonomy"]["judge_signals"]
    # telemetry aggregated from the §6 trace
    assert r["telemetry"]["turns"] > 0
    assert set(r["telemetry"]["by_component"]) >= {"planner", "reasoner", "self_eval"}
    assert r["tutor"]["provider"] == "stub"


# ── no_solution is DETERMINISTIC from the gate, not the judge ─────────────────


def test_no_solution_comes_from_the_gate_not_the_judge():
    # judge=None: the no_solution family must STILL produce a verdict (gate-derived).
    r = _report(repeats=2, judge=None)
    ns = r["families"]["no_solution"]
    assert ns["category"] == "gate_verdict"
    assert ns["trials"] == 5 * 2  # 5 scenarios x 2 repeats
    assert ns["passes"] == ns["trials"]  # the canned tutor never leaks


def test_gate_verdict_is_deterministic_on_text():
    from app.core.registry import get_active_pack
    from app.packs.datascience.solutions import SOLUTIONS  # tests may import packs

    h = Harness(get_active_pack(), CannedTutor(), None, 1, get_fixtures("datascience"))
    clean = {"message": "What does your held-out R^2 tell you about generalization?"}
    leak = {"message": "```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```"}
    assert h.gate(clean, "stuck_wants_example")["no_solution"] is True
    assert h.gate(leak, "stuck_wants_example")["no_solution"] is False  # ds-foundations solution


# ── the judge is separate; self-judging is refused ───────────────────────────


def test_self_judge_detection():
    same = compute_judge_meta("openai_compatible", {"llama3.2"}, "openai_compatible", "llama3.2")
    assert same["self_judged"] is True and same["credible"] is False
    diff = compute_judge_meta("openai_compatible", {"llama3.2"}, "openai_compatible", "qwen2.5:32b")
    assert diff["self_judged"] is False and diff["credible"] is True
    cross = compute_judge_meta("openai_compatible", {"llama3.2"}, "anthropic", "claude-sonnet-4-6")
    assert cross["self_judged"] is False


def test_report_marks_self_judged_families_not_credible():
    r = _report(
        repeats=2,
        judge=CannedJudge(credible=False),
        judge_meta={
            "provider": "openai_compatible",
            "model": "llama3.2",
            "self_judged": True,
            "credible": False,
        },
    )
    g = r["families"]["grounded"]
    assert g["credible"] is False
    assert "not credible" in (g["note"] or "").lower()
    assert r["judge"]["self_judged"] is True


# ── --repeats reports pass rates / distributions ─────────────────────────────


def test_repeats_reports_pass_rates_not_single_passes():
    r = _report(
        repeats=5,
        judge=CannedJudge(credible=True),
        judge_meta={"provider": "p", "model": "m", "self_judged": False, "credible": True},
    )
    ef = r["families"]["encourage_frustration"]
    assert ef["pass_rate"].endswith("/5") and ef["trials"] == 5 and "rate" in ef
    grounded = r["families"]["grounded"]  # 3 fixtures x 5 repeats
    assert grounded["pass_rate_vs_threshold"].endswith("/15")
    assert isinstance(grounded["distribution"], dict)


# ── family registry is pluggable (facilitator slots in later) ────────────────


def test_family_registry_is_pluggable():
    assert {"never_leak", "no_solution", "grounded"} <= set(registry())
    try:

        @family("facilitator_smoke", "framework_routing")
        def _f(h):
            return {"category": "framework_routing", "pass_rate": "0/0"}

        assert "facilitator_smoke" in registry()
    finally:
        fam_mod._REGISTRY.pop("facilitator_smoke", None)


# ── RUN_LLM_EVALS-gated live run (needs reachable tutor + judge) ──────────────


@pytest.mark.skipif(
    not os.environ.get("RUN_LLM_EVALS"),
    reason="set RUN_LLM_EVALS=1 with a reachable tutor + judge endpoint",
)
def test_live_benchmark_runs():
    from evals.behavioral.__main__ import main

    report = main(["--pack", "datascience", "--repeats", "1"])
    assert report["families"]["never_leak"]["trials"] >= 1
    assert report["families"]["no_solution"]["category"] == "gate_verdict"
