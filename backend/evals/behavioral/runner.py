"""
Benchmark runner — the credibility architecture.

Runs each registered family `--repeats` times and assembles a JSON report that:
  - records tutor provider+model AND judge provider+model, repeats, temperature;
  - reports per-family PASS RATES (not single passes), because single results flip;
  - takes no_solution and never_leak as DETERMINISTIC gate verdicts (not LLM rubrics);
  - keeps judge-scored families as signals, and marks them not-credible when the
    judge model equals the tutor model under test (a model cannot judge itself);
  - aggregates the §6 per-component telemetry (latency, tokens, cost).
"""

from __future__ import annotations

from app.core.domain import get_active_pack
from app.store import InMemoryStore

from .families import registry
from .fixtures import REVISIT_PREPOP, get_fixtures

_CAT_KEY = {
    "gate_verdict": "gate_verdicts",
    "framework_routing": "framework_routing",
    "judge_signal": "judge_signals",
}


class _Telemetry:
    """Aggregates §6 telemetry.component_usage across all turns run."""

    def __init__(self) -> None:
        self.turns = 0
        self._by: dict[str, dict] = {}

    def add(self, out: dict) -> None:
        self.turns += 1
        cu = (out.get("components") or {}).get("component_usage") or {}
        for role, e in cu.items():
            a = self._by.setdefault(
                role,
                {
                    "calls": 0,
                    "latency_ms": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cost": 0.0,
                    "_tok": False,
                    "_cost": False,
                },
            )
            a["calls"] += e.get("calls", 0)
            a["latency_ms"] = round(a["latency_ms"] + (e.get("latency_ms") or 0.0), 1)
            if e.get("prompt_tokens") is not None:
                a["prompt_tokens"] += e["prompt_tokens"]
                a["completion_tokens"] += e.get("completion_tokens") or 0
                a["_tok"] = True
            if e.get("cost") is not None:
                a["cost"] = round(a["cost"] + e["cost"], 6)
                a["_cost"] = True

    def report(self) -> dict:
        by, total_cost, has_cost = {}, 0.0, False
        for role, a in self._by.items():
            by[role] = {
                "calls": a["calls"],
                "latency_ms": a["latency_ms"],
                "prompt_tokens": a["prompt_tokens"] if a["_tok"] else None,
                "completion_tokens": a["completion_tokens"] if a["_tok"] else None,
                "cost": a["cost"] if a["_cost"] else None,
            }
            if a["_cost"]:
                total_cost += a["cost"]
                has_cost = True
        return {
            "turns": self.turns,
            "by_component": by,
            "total_cost": round(total_cost, 6) if has_cost else None,
        }


class Harness:
    def __init__(self, pack, tutor, judge, repeats: int, fixtures: dict) -> None:
        self.pack = pack
        self.tutor = tutor
        self.judge = judge
        self.repeats = repeats
        self.fixtures = fixtures
        self.telemetry = _Telemetry()

    def tutor_turn(self, name: str, goals: str | None = None) -> dict:
        from app.agent import run_turn

        store = InMemoryStore()
        payload = self.fixtures[name]
        prepop = REVISIT_PREPOP.get(name)
        if prepop:
            store.save_learner_state(payload["participant_id"], prepop)
        if goals:  # opt-in: set a learner goal before the turn (student-rule-cannot-leak)
            from app.agent.goals import set_goals

            set_goals(store, payload["participant_id"], goals)
        out = run_turn(payload, self.tutor, store)
        self.telemetry.add(out)
        return out

    def gate(self, out: dict, name: str) -> dict:
        """DETERMINISTIC gate verdict on the emitted message — never an LLM call."""
        ev = self.pack.leak_evidence(out["message"], self.fixtures[name]["exercise"])
        return {
            "is_solution": ev.is_solution,
            "prose_disclosure": ev.prose_disclosure,
            "no_solution": (not ev.is_solution) and (not ev.prose_disclosure),
        }

    def situation(self, name: str) -> dict:
        fx = self.fixtures[name]
        return {
            "source": fx.get("source"),
            "result": fx.get("result"),
            "recent": fx.get("recent"),
            "signals": fx.get("signals"),
        }


def run_benchmark(
    *,
    pack_id: str,
    tutor,
    judge,
    repeats: int,
    tutor_meta: dict,
    judge_meta: dict,
    temperature: float,
    families: list[str] | None = None,
) -> dict:
    pack = get_active_pack()
    fixtures = get_fixtures(pack_id)
    fams = registry()
    selected = families or list(fams)
    h = Harness(pack, tutor, judge, repeats, fixtures)

    results = {name: fams[name].run(h) for name in selected}

    taxonomy = {"gate_verdicts": [], "framework_routing": [], "judge_signals": []}
    for name in selected:
        taxonomy[_CAT_KEY[fams[name].category]].append(name)

    return {
        "benchmark": "behavioral",
        "pack": pack_id,
        "repeats": repeats,
        "temperature": temperature,
        "tutor": tutor_meta,
        "judge": judge_meta,
        "families": results,
        "taxonomy": taxonomy,
        "telemetry": h.telemetry.report(),
        "notes": [
            "no_solution and never_leak are DETERMINISTIC gate verdicts, not LLM rubrics.",
            "framework_routing pass rates reflect the model's classification as much as the framework.",
            "judge-scored families are signals, not verdicts; not credible when self-judged.",
            "facilitator family is pending Phase 5 (slots into the family registry).",
        ],
    }
