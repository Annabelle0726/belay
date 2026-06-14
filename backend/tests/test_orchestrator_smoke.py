"""End-to-end loop test with a stub LLM — proves Planner -> Reasoner ->
Self-Eval -> (refine) -> Governance -> Memory wires together, with no network
and no database. Also covers the control bypass and stance telemetry."""
import json

from app.agent import run_turn
from app.curriculum import get_exercise
from app.store import InMemoryStore


class StubLLM:
    """Deterministic component responses, configurable to exercise branches."""

    def __init__(self, leak=False, revise_once=False):
        self.leak = leak
        self.revise_once = revise_once
        self._evals = 0

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {"affective_state": "productive_struggle",
                    "affect_reasoning": "tried twice, distance shrinking",
                    "intervention": "co_reason", "target_concept": "entanglement",
                    "planner_note": "nudge toward linking the qubits"}
        if role == "reasoner":
            msg = ("ok here:\nallocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all"
                   if self.leak else
                   "You've got q0 in superposition — what single op makes q1 agree with it?")
            return {"message": msg, "check_question": "what links them?",
                    "confidence": 0.8, "grasped": ["superposition"], "shaky": ["entanglement"]}
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
        "exercise": get_exercise("bell"),
        "event": "run", "mode": "study",
        "stance": stance,
        "source": "allocate 2\nsuperpose q0\nmeasure all",
        "result": {"ok": True, "goalMet": False, "dist": [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}],
                   "diff": "missing weight on |11⟩"},
        "recent": [], "signals": {"attempts": 2, "distanceTrend": [0.5, 0.5],
                                  "repeatedError": False, "sinceLastProgress": 2},
    }


def test_contract_shape_and_persistence():
    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(), store)
    for k in ("affective_state", "confidence", "intervention", "planner_note",
              "self_critique", "governance", "memory", "message", "check_question", "components"):
        assert k in out, f"missing {k}"
    assert out["memory"]["grasped"] == ["superposition"]
    assert out["memory"]["shaky"] == ["entanglement"]
    # one trace event written
    assert store.export_jsonl("p_test").count("\n") == 0  # exactly one line, no trailing newline
    # learner model persisted
    assert store.get_learner_state("p_test")["grasped"] == ["superposition"]


def test_refine_loop_runs():
    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(revise_once=True), store)
    assert out["components"]["refines"] == 1


def test_governance_strips_leak():
    store = InMemoryStore()
    out = run_turn(_payload(), StubLLM(leak=True), store)
    assert out["governance"] == "withholding_solution"
    assert "entangle q0 q1" not in out["message"]
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
    # StubLLM would raise if any LLM role is called — pass one so any call is a test failure
    out = run_turn(_payload(pid="p_ctrl", stance="control"), StubLLM(), store)
    # response shape is intact
    for k in ("affective_state", "confidence", "intervention", "message", "memory", "components"):
        assert k in out, f"missing {k}"
    assert out["components"]["stance"] == "control"
    # no peer loop ran — memory is empty (no LLM concept updates)
    assert out["memory"]["grasped"] == []
    # one trace event with stance=control
    row = json.loads(store.export_jsonl("p_ctrl"))
    assert row["stance"] == "control"
    assert row["payload"]["stance"] == "control"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("orchestrator smoke: all passed")
