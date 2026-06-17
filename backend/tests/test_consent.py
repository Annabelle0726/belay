# SPDX-License-Identifier: AGPL-3.0-only
"""
Consent-gated logging tests (DMP §3 / IRB).

All tests are offline: the ConsentRouter is backed by an InMemoryStore so no
database file is created or read.  The router tracks consent in its own cache;
the durable InMemoryStore serves as the stand-in for the SqlStore (events and
learner state written to it are checked directly).

Four scenarios tested:
  consenting     — events + learner state reach the durable store; export non-empty
  non-consenting — events + learner state go to ephemeral; export empty; session OK
  fail-safe      — unregistered pid also goes to ephemeral; nothing durable written
  identical      — run_turn output is identical regardless of consent
"""

from __future__ import annotations

from app.agent import run_turn
from app.core.registry import get_active_pack
from app.store import InMemoryStore, make_event
from app.store.consent import ConsentRouter

_EX = get_active_pack().get_exercise("ds-foundations")


# ── minimal deterministic stub LLM (no network) ───────────────────────────────


class _StubLLM:
    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "planner":
            return {
                "affective_state": "curious",
                "affect_reasoning": "stub",
                "intervention": "co_reason",
                "target_concept": "entanglement",
                "planner_note": "guide them",
                "confidence": 0.7,
            }
        if role == "reasoner":
            return {
                "message": "Think about what links the qubits.",
                "check_question": None,
                "confidence": 0.8,
                "grasped": ["superposition"],
                "shaky": ["entanglement"],
            }
        if role == "self_eval":
            return {
                "needs_revision": False,
                "confidence": 0.75,
                "leak_risk": "none",
                "self_critique": "ok",
                "reasons": [],
            }
        raise AssertionError(f"unexpected role: {role}")


def _payload(pid: str, stance: str = "peer") -> dict:
    return {
        "participant_id": pid,
        "exercise": _EX,
        "event": "run",
        "mode": "study",
        "stance": stance,
        "source": "import pandas as pd\ndf = pd.read_csv('data/sales.csv')",
        "result": {
            "ok": True,
            "goalMet": False,
            "metric": 0.5,
            "pack": {"id": "datascience", "summary": "0/1 checks passed"},
        },
        "recent": [],
        "signals": {
            "attempts": 1,
            "distanceTrend": [0.5],
            "repeatedError": False,
            "sinceLastProgress": 1,
        },
    }


def _make_router():
    """Fresh router backed by an InMemoryStore (no SQL needed)."""
    return ConsentRouter(InMemoryStore())


# ── tests ─────────────────────────────────────────────────────────────────────


class TestConsentRouting:
    """ConsentRouter routes correctly for the three registration states."""

    def test_store_for_consented_returns_durable(self):
        router = _make_router()
        router.register_participant("p1", "code1", consent=True)
        assert router.store_for("p1") is router.durable

    def test_store_for_not_consented_returns_ephemeral(self):
        router = _make_router()
        router.register_participant("p2", "code2", consent=False)
        store = router.store_for("p2")
        assert store is not router.durable
        assert isinstance(store, InMemoryStore)

    def test_store_for_unregistered_returns_ephemeral_failsafe(self):
        """Fail-safe: unregistered pid → ephemeral, never the durable store."""
        router = _make_router()
        store = router.store_for("p_unknown")
        assert store is not router.durable
        assert isinstance(store, InMemoryStore)

    def test_same_pid_always_same_ephemeral_instance(self):
        """Repeated store_for calls for the same non-consenting pid return the
        same InMemoryStore so learner state accumulates correctly in-session."""
        router = _make_router()
        router.register_participant("p3", "code3", consent=False)
        s1 = router.store_for("p3")
        s2 = router.store_for("p3")
        assert s1 is s2


class TestConsentingParticipant:
    """consent=True → events + learner state reach the durable store."""

    def test_events_in_durable_after_run_event(self):
        router = _make_router()
        pid = "p_yes"
        router.register_participant(pid, "c1", consent=True)
        store = router.store_for(pid)
        store.append_event(
            make_event(
                pid, "ds-foundations", "study", "run", {"source": "x", "result": {}}, stance="peer"
            )
        )
        # Export reads from durable → non-empty
        jsonl = router.durable.export_jsonl(pid)
        assert jsonl.strip() != ""
        assert pid in jsonl

    def test_learner_state_in_durable_after_sol_turn(self):
        router = _make_router()
        pid = "p_yes_state"
        router.register_participant(pid, "c2", consent=True)
        store = router.store_for(pid)
        run_turn(_payload(pid), _StubLLM(), store)
        # Learner state persisted to durable
        state = router.durable.get_learner_state(pid)
        assert "superposition" in state["grasped"] or "entanglement" in state["shaky"]

    def test_export_non_empty_for_consented(self):
        router = _make_router()
        pid = "p_export"
        router.register_participant(pid, "c3", consent=True)
        store = router.store_for(pid)
        run_turn(_payload(pid), _StubLLM(), store)
        jsonl = router.durable.export_jsonl(pid)
        assert jsonl.strip() != ""


class TestNonConsentingParticipant:
    """consent=False → events + learner state are ephemeral; export stays empty."""

    def test_events_not_in_durable(self):
        router = _make_router()
        pid = "p_no"
        router.register_participant(pid, "c4", consent=False)
        store = router.store_for(pid)
        store.append_event(
            make_event(
                pid, "ds-foundations", "study", "run", {"source": "x", "result": {}}, stance="peer"
            )
        )
        # Durable export must be empty for this pid
        assert router.durable.export_jsonl(pid).strip() == ""

    def test_session_still_works_end_to_end(self):
        """Non-consenting session completes normally; output is valid."""
        router = _make_router()
        pid = "p_no_session"
        router.register_participant(pid, "c5", consent=False)
        store = router.store_for(pid)
        out = run_turn(_payload(pid), _StubLLM(), store)
        # Full tutoring response is returned
        for key in ("message", "intervention", "confidence", "governance", "memory"):
            assert key in out, f"missing key: {key}"

    def test_learner_state_not_in_durable(self):
        router = _make_router()
        pid = "p_no_state"
        router.register_participant(pid, "c6", consent=False)
        store = router.store_for(pid)
        run_turn(_payload(pid), _StubLLM(), store)
        # Durable store has no learner state for this pid
        state = router.durable.get_learner_state(pid)
        assert state["grasped"] == []
        assert state["shaky"] == []

    def test_export_empty_for_non_consented(self):
        router = _make_router()
        pid = "p_no_export"
        router.register_participant(pid, "c7", consent=False)
        run_turn(_payload(pid), _StubLLM(), router.store_for(pid))
        assert router.durable.export_jsonl(pid).strip() == ""


class TestFailSafe:
    """Unregistered pid → ephemeral; nothing reaches durable."""

    def test_run_event_not_durable_before_registration(self):
        router = _make_router()
        pid = "p_unregistered"
        # Interact WITHOUT registering
        store = router.store_for(pid)
        store.append_event(
            make_event(
                pid, "ds-foundations", "study", "run", {"source": "x", "result": {}}, stance="peer"
            )
        )
        assert router.durable.export_jsonl(pid).strip() == ""

    def test_sol_turn_not_durable_before_registration(self):
        router = _make_router()
        pid = "p_unregistered_turn"
        # Full sol turn without prior registration
        store = router.store_for(pid)
        out = run_turn(_payload(pid), _StubLLM(), store)
        assert out["message"]  # session works
        assert router.durable.export_jsonl(pid).strip() == ""  # nothing persisted
        state = router.durable.get_learner_state(pid)
        assert state["grasped"] == []


class TestTutoringOutputIdentical:
    """Tutoring output must be byte-for-byte identical regardless of consent."""

    def test_run_turn_output_same_for_consented_vs_not(self):
        router = _make_router()
        pid_yes = "p_out_yes"
        pid_no = "p_out_no"
        router.register_participant(pid_yes, "cy", consent=True)
        router.register_participant(pid_no, "cn", consent=False)

        llm = _StubLLM()  # deterministic: same inputs → same outputs
        out_yes = run_turn(_payload(pid_yes), llm, router.store_for(pid_yes))
        out_no = run_turn(_payload(pid_no), llm, router.store_for(pid_no))

        assert out_yes["message"] == out_no["message"]
        assert out_yes["intervention"] == out_no["intervention"]
        assert out_yes["confidence"] == out_no["confidence"]
        assert out_yes["governance"] == out_no["governance"]
        assert out_yes["affective_state"] == out_no["affective_state"]

    def test_run_turn_output_same_for_unregistered(self):
        """Unregistered (fail-safe ephemeral) also produces identical output."""
        router_with = _make_router()
        router_with.register_participant("p_w", "cw", consent=True)

        router_without = _make_router()
        # No register_participant for "p_wo"

        llm = _StubLLM()
        out_with = run_turn(_payload("p_w"), llm, router_with.store_for("p_w"))
        out_without = run_turn(_payload("p_wo"), llm, router_without.store_for("p_wo"))

        assert out_with["message"] == out_without["message"]
