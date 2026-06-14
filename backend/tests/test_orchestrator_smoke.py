"""End-to-end loop test with a stub LLM (DS fixtures) — proves Planner ->
Reasoner -> Self-Eval -> (refine) -> Governance -> Memory wires together, with no
network and no database. Also covers the control bypass and stance telemetry."""
import json

from app.agent import run_turn
from app.core.domain import get_active_pack
from app.packs.datascience.solutions import SOLUTIONS
from app.store import InMemoryStore

_EX = get_active_pack().get_exercise("ds-foundations")
_LEAK_MSG = "ok here:\n```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```"


class StubLLM:
    """Deterministic component responses, configurable to exercise branches."""

    def __init__(self, leak=False, revise_once=False):
        self.leak = leak
        self.revise_once = revise_once
        self._evals = 0

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {"affective_state": "productive_struggle",
                    "affect_reasoning": "tried twice, getting closer",
                    "intervention": "co_reason", "target_concept": "group-by",
                    "planner_note": "nudge toward aggregating each group"}
        if role == "reasoner":
            msg = (_LEAK_MSG if self.leak else
                   "You've read the CSV — what one number should each category collapse to?")
            return {"message": msg, "check_question": "what summarizes a group?",
                    "confidence": 0.8, "grasped": ["reading-csv"], "shaky": ["aggregation"]}
        if role == "self_eval":
            self._evals += 1
            needs = self.revise_once and self._evals == 1
            return {"needs_revision": needs, "confidence": 0.62,
                    "leak_risk": "none", "self_critique": "checked against their last run",
                    "reasons": (["over-helping"] if needs else [])}
        raise AssertionError(role)


def _payload(pid="p_test", stance="peer"):
    return {
        "participant_id": pid,
        "exercise": _EX,
        "event": "run", "mode": "study",
        "stance": stance,
        "source": "import pandas as pd\ndf = pd.read_csv('data/sales.csv')",
        "result": {"ok": True, "goalMet": False, "metric": None,
                   "pack": {"id": "datascience", "summary": "0/1 checks passed"}},
        "recent": [], "signals": {"attempts": 2, "distanceTrend": [0.5, 0.5],
                                  "repeatedError": False, "sinceLastProgress": 2},
    }


def test_contract_shape_and_persistence():
    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(), store)
    for k in ("affective_state", "confidence", "intervention", "planner_note",
              "self_critique", "governance", "memory", "message", "check_question", "components"):
        assert k in out, f"missing {k}"
    assert out["memory"]["grasped"] == ["reading-csv"]
    assert out["memory"]["shaky"] == ["aggregation"]
    # one trace event written
    assert store.export_jsonl("p_test").count("\n") == 0  # exactly one line, no trailing newline
    # learner model persisted
    assert store.get_learner_state("p_test")["grasped"] == ["reading-csv"]


def test_refine_loop_runs():
    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(revise_once=True), store)
    assert out["components"]["refines"] == 1


def test_governance_strips_leak():
    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(leak=True), store)
    assert out["governance"] == "withholding_solution"
    assert "groupby" not in out["message"]
    assert out["confidence"] <= 0.6


def test_peer_event_carries_stance():
    """Every emitted event must include stance."""
    store = InMemoryStore()
    run_turn(_payload(pid="p_peer", stance="peer"), StubLLM(), store)
    row = json.loads(store.export_jsonl("p_peer"))
    assert row["stance"] == "peer"
    assert row["payload"]["stance"] == "peer"


def test_control_bypasses_loop_and_emits_event():
    """control: no planner/reasoner/self_eval; trace event has stance='control'."""
    store = InMemoryStore()
    out = run_turn(_payload(pid="p_ctrl", stance="control"), StubLLM(), store)
    for k in ("affective_state", "confidence", "intervention", "message", "memory", "components"):
        assert k in out, f"missing {k}"
    assert out["components"]["stance"] == "control"
    assert out["memory"]["grasped"] == []
    row = json.loads(store.export_jsonl("p_ctrl"))
    assert row["stance"] == "control"
    assert row["payload"]["stance"] == "control"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("orchestrator smoke: all passed")
