"""
RQ2/H2 stance integration tests.

Verifies all three stance branches under a StubLLM so no network or database
is needed. Key invariants:
  peer    — full loop runs; no-leak self-eval rubric + withholding_solution
            gate + redirect_answer_seeking are active; escalate/reciprocate
            available.
  oracle  — SAME full loop (matched capability/effort); only the stance prompts,
            the self-eval rubric (grounded/correct/clear), and which gates fire
            differ. withholding_solution + redirect_answer_seeking are OFF, the
            answer survives refine, and escalate/reciprocate are not offered.
  control — loop is bypassed entirely; canned message returned; event emitted.
"""
import json

from app.agent import run_turn
from app.agent.prompts import (
    ABSTAIN_MESSAGE,
    CONTROL_MESSAGE,
    ORACLE_PLANNER_SYSTEM,
    ORACLE_REASONER_SYSTEM,
    ORACLE_SELFEVAL_SYSTEM,
    PLANNER_SYSTEM,
    REASONER_SYSTEM,
    SELFEVAL_SYSTEM,
)
from app.config import settings
from app.curriculum import get_exercise
from app.store import InMemoryStore

BELL = get_exercise("bell")
_SOLUTION_MSG = "allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all"
_ANSWER_SEEKING = [{"who": "student", "text": "just tell me the answer please"}]

# Scripted self-eval confidences relative to the configured thresholds
# (tau_escalate=0.55, tau_abstain=0.35), so the tests read intent clearly.
_CONF_HIGH = 0.80           # >= tau_escalate: no escalation, no abstention
_CONF_ESCALATE_ONLY = 0.45  # in [tau_abstain, tau_escalate): escalate, don't abstain
_CONF_FLOOR = 0.20          # < tau_abstain: escalate, then peer abstains


class StubLLM:
    """Deterministic, rubric-faithful component stub.

    - planner returns a configurable intervention + confidence.
    - reasoner returns either a full-solution draft (leak=True) or a hint, and
      records the per-call reasoning_effort it was handed (the escalation lever).
    - self_eval is rubric-faithful (peer revises a leak; oracle never does) and
      returns a SCRIPTED confidence so escalation/abstention can be exercised.
    """

    def __init__(self, leak=False, planner_intervention="co_reason",
                 eval_confidence=0.75, planner_confidence=0.70, reasoner_confidence=0.80):
        self.leak = leak
        self.planner_intervention = planner_intervention
        self.eval_confidence = eval_confidence
        self.planner_confidence = planner_confidence
        self.reasoner_confidence = reasoner_confidence
        self.seen_systems: list[str] = []
        self.seen_eval_systems: list[str] = []
        self.seen_efforts: list = []   # reasoning_effort per reasoner call

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        self.seen_systems.append(system)
        if role == "planner":
            return {"affective_state": "curious",
                    "affect_reasoning": "first attempt",
                    "intervention": self.planner_intervention,
                    "target_concept": "entanglement", "planner_note": "guide them",
                    "confidence": self.planner_confidence}
        if role == "reasoner":
            self.seen_efforts.append(reasoning_effort)
            msg = _SOLUTION_MSG if self.leak else "Think about what links the two qubits."
            return {"message": msg, "check_question": None,
                    "confidence": self.reasoner_confidence,
                    "grasped": ["superposition"], "shaky": ["entanglement"]}
        if role == "self_eval":
            self.seen_eval_systems.append(system)
            # Oracle rubric never penalizes answering; peer rubric revises a leak.
            needs = False if system == ORACLE_SELFEVAL_SYSTEM else self.leak
            return {"needs_revision": needs, "confidence": self.eval_confidence,
                    "leak_risk": ("full" if self.leak else "none"),
                    "self_critique": "looks reasonable", "reasons": []}
        raise AssertionError(f"unexpected role: {role}")


def _payload(pid: str, stance: str, recent=None) -> dict:
    return {
        "participant_id": pid,
        "exercise": BELL,
        "event": "run", "mode": "study",
        "stance": stance,
        "source": "allocate 2\nsuperpose q0\nmeasure all",
        "result": {"ok": True, "goalMet": False,
                   "dist": [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}],
                   "diff": "missing |11⟩"},
        "recent": recent or [], "signals": {"attempts": 1, "distanceTrend": [0.5],
                                  "repeatedError": False, "sinceLastProgress": 1},
    }


# ── peer ──────────────────────────────────────────────────────────────────────

class TestPeerStance:
    def test_uses_peer_prompts(self):
        llm = StubLLM()
        run_turn(_payload("p1", "peer"), llm, InMemoryStore())
        assert any(PLANNER_SYSTEM in s for s in llm.seen_systems)
        assert any(REASONER_SYSTEM in s for s in llm.seen_systems)

    def test_solution_is_blocked(self):
        store = InMemoryStore()
        out = run_turn(_payload("p2", "peer"), StubLLM(leak=True), store)
        assert out["governance"] == "withholding_solution"
        assert _SOLUTION_MSG not in out["message"]

    def test_stance_in_event(self):
        store = InMemoryStore()
        run_turn(_payload("p3", "peer"), StubLLM(), store)
        row = json.loads(store.export_jsonl("p3"))
        assert row["stance"] == "peer"
        assert row["payload"]["stance"] == "peer"

    def test_memory_updated(self):
        store = InMemoryStore()
        run_turn(_payload("p4", "peer"), StubLLM(), store)
        assert "superposition" in store.get_learner_state("p4")["grasped"]

    def test_self_eval_uses_peer_rubric(self):
        llm = StubLLM()
        run_turn(_payload("p5", "peer"), llm, InMemoryStore())
        assert SELFEVAL_SYSTEM in llm.seen_eval_systems
        assert ORACLE_SELFEVAL_SYSTEM not in llm.seen_eval_systems

    def test_leak_triggers_refine(self):
        """peer rubric: a leaked full solution forces a revision."""
        out = run_turn(_payload("p6", "peer"), StubLLM(leak=True), InMemoryStore())
        assert out["components"]["refines"] >= 1

    def test_escalate_flags_for_instructor(self):
        """peer keeps escalate → governance flags it for the instructor."""
        out = run_turn(_payload("p7", "peer"), StubLLM(planner_intervention="escalate"),
                       InMemoryStore())
        assert out["intervention"] == "escalate"
        assert out["governance"] == "flag_escalate"

    def test_answer_seeking_is_redirected(self):
        out = run_turn(_payload("p8", "peer", recent=_ANSWER_SEEKING),
                       StubLLM(leak=False), InMemoryStore())
        assert out["governance"] == "redirect_answer_seeking"


# ── oracle ────────────────────────────────────────────────────────────────────

class TestOracleStance:
    def test_uses_oracle_prompts(self):
        llm = StubLLM()
        run_turn(_payload("o1", "oracle"), llm, InMemoryStore())
        assert any(ORACLE_PLANNER_SYSTEM in s for s in llm.seen_systems)
        assert any(ORACLE_REASONER_SYSTEM in s for s in llm.seen_systems)

    def test_solution_is_allowed(self):
        store = InMemoryStore()
        out = run_turn(_payload("o2", "oracle"), StubLLM(leak=True), store)
        assert out["governance"] != "withholding_solution"
        # solution code must reach the student unchanged
        assert _SOLUTION_MSG in out["message"]

    def test_stance_in_event(self):
        store = InMemoryStore()
        run_turn(_payload("o3", "oracle"), StubLLM(), store)
        row = json.loads(store.export_jsonl("o3"))
        assert row["stance"] == "oracle"
        assert row["payload"]["stance"] == "oracle"

    def test_memory_updated(self):
        store = InMemoryStore()
        run_turn(_payload("o4", "oracle"), StubLLM(), store)
        assert "superposition" in store.get_learner_state("o4")["grasped"]

    def test_self_eval_uses_oracle_rubric(self):
        llm = StubLLM()
        run_turn(_payload("o5", "oracle"), llm, InMemoryStore())
        assert ORACLE_SELFEVAL_SYSTEM in llm.seen_eval_systems
        assert SELFEVAL_SYSTEM not in llm.seen_eval_systems

    def test_full_solution_passes_rubric_no_refine(self):
        """oracle rubric: a full-solution draft does NOT trigger needs_revision,
        and refine does not water the answer down."""
        out = run_turn(_payload("o6", "oracle"), StubLLM(leak=True), InMemoryStore())
        assert out["components"]["refines"] == 0
        assert _SOLUTION_MSG in out["message"]      # answer survives intact

    def test_answer_seeking_not_redirected(self):
        """oracle: an answered answer-seeking turn reads as 'none', not redirect."""
        out = run_turn(_payload("o7", "oracle", recent=_ANSWER_SEEKING),
                       StubLLM(leak=False), InMemoryStore())
        assert out["governance"] == "none"

    def test_planner_never_escalates_or_reciprocates(self):
        """oracle planner menu has no escalate/reciprocate; the guard coerces
        either to a valid answer-giving move, so flag_escalate can't fire."""
        for forced in ("escalate", "reciprocate"):
            out = run_turn(_payload("o8", "oracle"),
                           StubLLM(planner_intervention=forced), InMemoryStore())
            assert out["intervention"] not in ("escalate", "reciprocate"), forced
            assert out["governance"] != "flag_escalate", forced


# ── control ───────────────────────────────────────────────────────────────────

class TestControlStance:
    def test_no_llm_calls(self):
        """control must not call the LLM at all."""
        class NeverCallLLM:
            def json(self, **_):
                raise AssertionError("LLM must not be called in control condition")

        store = InMemoryStore()
        run_turn(_payload("c1", "control"), NeverCallLLM(), store)  # must not raise

    def test_returns_canned_message(self):
        store = InMemoryStore()
        out = run_turn(_payload("c2", "control"), StubLLM(), store)
        assert out["message"] == CONTROL_MESSAGE

    def test_response_shape_intact(self):
        store = InMemoryStore()
        out = run_turn(_payload("c3", "control"), StubLLM(), store)
        for k in ("affective_state", "confidence", "intervention", "planner_note",
                  "self_critique", "governance", "memory", "message", "components"):
            assert k in out, f"missing key: {k}"

    def test_stance_in_event(self):
        store = InMemoryStore()
        run_turn(_payload("c4", "control"), StubLLM(), store)
        row = json.loads(store.export_jsonl("c4"))
        assert row["stance"] == "control"
        assert row["payload"]["stance"] == "control"

    def test_components_stance_field(self):
        store = InMemoryStore()
        out = run_turn(_payload("c5", "control"), StubLLM(), store)
        assert out["components"]["stance"] == "control"


# ── escalation: capability lever, applied IDENTICALLY to peer and oracle ───────

class TestEscalation:
    def test_high_confidence_no_escalation_either_arm(self):
        for stance in ("peer", "oracle"):
            llm = StubLLM(eval_confidence=_CONF_HIGH)
            out = run_turn(_payload(f"e_hi_{stance}", stance), llm, InMemoryStore())
            assert out["components"]["escalated"] is False, stance
            assert out["components"]["abstained"] is False, stance
            assert out["components"]["reasoning_effort"] == settings.reasoner_effort_default, stance
            assert "high" not in llm.seen_efforts, stance      # never re-ran at high effort

    def test_low_confidence_escalates_at_higher_effort(self):
        """Below tau_escalate (but above the abstain floor) → one high-effort re-run."""
        for stance in ("peer", "oracle"):
            llm = StubLLM(eval_confidence=_CONF_ESCALATE_ONLY)
            out = run_turn(_payload(f"e_lo_{stance}", stance), llm, InMemoryStore())
            assert out["components"]["escalated"] is True, stance
            assert out["components"]["abstained"] is False, stance      # above the floor
            assert out["components"]["reasoning_effort"] == settings.reasoner_effort_escalated, stance
            assert llm.seen_efforts[0] == settings.reasoner_effort_default, stance
            assert settings.reasoner_effort_escalated in llm.seen_efforts, stance

    def test_escalation_is_bounded(self):
        llm = StubLLM(eval_confidence=_CONF_FLOOR)   # stays low → would loop unbounded
        run_turn(_payload("e_bound", "oracle"), llm, InMemoryStore())
        # exactly MAX_ESCALATE high-effort re-runs (default 1)
        assert llm.seen_efforts.count(settings.reasoner_effort_escalated) == settings.max_escalate


# ── abstention: stance behavior, PEER ONLY ────────────────────────────────────

class TestAbstention:
    def test_peer_abstains_below_floor(self):
        out = run_turn(_payload("ab_peer", "peer"), StubLLM(eval_confidence=_CONF_FLOOR),
                       InMemoryStore())
        assert out["components"]["escalated"] is True       # escalation tried first
        assert out["components"]["abstained"] is True
        assert out["intervention"] == "escalate"            # override, independent of planner
        assert out["governance"] == "flag_escalate"         # gov escalate flag stays consistent
        assert out["message"] == ABSTAIN_MESSAGE
        assert _SOLUTION_MSG not in out["message"]          # no confident full answer
        assert out["confidence"] <= settings.tau_abstain    # headline reflects the low confidence

    def test_oracle_never_abstains_below_floor(self):
        """Same low confidence + same escalation, but oracle answers — not abstains.
        Confirms capability is matched while stance differs."""
        llm = StubLLM(eval_confidence=_CONF_FLOOR)
        out = run_turn(_payload("ab_oracle", "oracle"), llm, InMemoryStore())
        assert out["components"]["escalated"] is True       # identical escalation
        assert out["components"]["abstained"] is False      # never abstains
        assert out["message"] != ABSTAIN_MESSAGE
        assert out["intervention"] != "escalate"            # planner's move is not overridden

    def test_control_never_escalates_or_abstains(self):
        out = run_turn(_payload("ab_ctrl", "control"), StubLLM(eval_confidence=_CONF_FLOOR),
                       InMemoryStore())
        assert out["components"]["escalated"] is False
        assert out["components"]["abstained"] is False


# ── per-agent confidence trajectory (both arms) ───────────────────────────────

class TestConfidenceTrajectory:
    def test_trajectory_present_both_arms(self):
        for stance in ("peer", "oracle"):
            store = InMemoryStore()
            out = run_turn(_payload(f"ct_{stance}", stance), StubLLM(), store)
            traj = out["components"]["confidence_trajectory"]
            for leg in ("planner", "reasoner", "self_eval"):
                assert isinstance(traj[leg], float), (stance, leg)
            # planner confidence also surfaced under components.planner
            assert isinstance(out["components"]["planner"]["confidence"], float), stance
            # and the trajectory is persisted on the trace event
            row = json.loads(store.export_jsonl(f"ct_{stance}"))
            assert row["payload"]["telemetry"]["confidence_trajectory"]["self_eval"] == traj["self_eval"]

    def test_control_trajectory_is_null(self):
        out = run_turn(_payload("ct_ctrl", "control"), StubLLM(), InMemoryStore())
        traj = out["components"]["confidence_trajectory"]
        assert traj == {"planner": None, "reasoner": None, "self_eval": None}
        assert out["components"]["reasoning_effort"] is None


if __name__ == "__main__":
    import sys
    failed = 0
    for cls in (TestPeerStance, TestOracleStance, TestControlStance,
                TestEscalation, TestAbstention, TestConfidenceTrajectory):
        obj = cls()
        for name in [m for m in dir(cls) if m.startswith("test_")]:
            try:
                getattr(obj, name)()
                print("PASS", cls.__name__, name)
            except Exception as e:
                print("FAIL", cls.__name__, name, "→", e)
                failed += 1
    sys.exit(failed)
