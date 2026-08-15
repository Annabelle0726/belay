# SPDX-License-Identifier: AGPL-3.0-only
"""
Tests for groundedness.py (CC-B3).

Follows test_distress.py pattern:
- Explicit grounded case: response traceable to passage → citation attached
- Ungrounded case: claim not traceable → flagged in trace, response unchanged
- Leak gate integrity: only sees passages that survived screen_passages
- No-op when knowledge() returns None
"""

from __future__ import annotations

from app.agent import groundedness
from app.config import settings
from app.core.registry import get_active_pack
from app.store import InMemoryStore
from conftest import _CallStub, _payload

_EX = get_active_pack().get_exercise("ds-foundations")


# ── Unit tests ──────────────────────────────────────────────────────────────


def test_extract_claims_from_response():
    """Test that substantive claims are extracted from response text."""
    response = (
        "The mean of category A is approximately 15. "
        "Category B has a mean of about 40. "
        "Let's think about what this tells us."
    )
    claims = groundedness._extract_claims(response)
    assert len(claims) >= 2
    assert "mean of category A is approximately 15" in " ".join(claims)
    assert "Category B has a mean of about 40" in " ".join(claims)


def test_grounded_response_cites_passage():
    """Test that a grounded response gets citations attached."""
    passages = [
        {
            "id": "passage_1",
            "text": "The mean of category A is 15 and category B is 40.",
            "citation": "Introduction to Statistics, Section 3.2",
            "locator": "https://docs.example.com/statistics/mean",
        }
    ]
    response = "The mean of category A is approximately 15, and category B is approximately 40."

    updated, trace = groundedness.check_groundedness(response, passages)

    # Should have citations
    assert "References:" in updated
    assert "[1]" in updated
    assert "Introduction to Statistics" in updated
    # Trace should record what was used
    assert trace["citations_used"] == ["passage_1"]
    assert trace["all_claims_grounded"] is True


def test_ungrounded_claim_flagged_in_trace():
    """Test that ungrounded claims are flagged in trace, response unchanged."""
    passages = [
        {
            "id": "passage_1",
            "text": "The mean of category A is 15.",
            "citation": "Introduction to Statistics, Section 3.2",
            "locator": "https://docs.example.com/statistics/mean",
        }
    ]
    response = "The mean of category B is approximately 40."  # Not in passage

    updated, trace = groundedness.check_groundedness(response, passages)

    assert updated == response
    assert trace["ungrounded_fragments"] == ["The mean of category B is approximately 40."]
    assert trace["all_claims_grounded"] is False
    assert trace["citations_used"] == []


def test_groundedness_no_op_when_no_passages():
    """Test that groundedness is a no-op when no passages are available."""
    response = "The mean is 15."

    updated, trace = groundedness.check_groundedness(response, [])

    assert updated == response
    assert trace["check_ran"] is False
    assert trace["reason"] == "no passages available"


def test_groundedness_no_op_when_no_claims():
    """Test that groundedness is a no-op when response has no substantive claims."""
    passages = [
        {
            "id": "passage_1",
            "text": "The mean is 15.",
            "citation": "Statistics 101",
            "locator": None,
        }
    ]
    response = "That's a good question! Let's think about it."

    updated, trace = groundedness.check_groundedness(response, passages)

    assert updated == response
    assert trace["check_ran"] is True
    assert trace["reason"] == "no substantive claims found"


# ── Integration tests ───────────────────────────────────────────────────────


def test_leak_gate_still_runs_before_groundedness(monkeypatch):
    """Confirm the leak gate still runs and drops solution-bearing passages
    before groundedness check ever sees them."""
    from app.agent.context import build_context

    # Use a real exercise and real pack
    pack = get_active_pack()
    # ✅ 添加 _ 前缀表示未使用，或直接使用
    _ = pack.get_exercise("ds-foundations")  # 不需要存储
    store = InMemoryStore()
    learner = store.get_learner_state("p_test")

    # Build context (which calls screen_passages)
    payload = _payload("p_test", "What is the mean?", exercise_id="ds-foundations")
    ctx = build_context(payload, learner, 0)

    # Knowledge should only contain passages that survived screen_passages
    knowledge = ctx.get("knowledge", [])
    retrieval = ctx.get("_retrieval", {})

    # Verify: any dropped passages are recorded (not in knowledge)
    if retrieval.get("dropped"):
        dropped_ids = [d["id"] for d in retrieval["dropped"]]
        knowledge_ids = [p["id"] for p in knowledge]
        assert all(d not in knowledge_ids for d in dropped_ids)

    # Groundedness only sees knowledge, which already had solution stripped
    if knowledge:
        updated, trace = groundedness.check_groundedness("test", knowledge)
        assert trace["passages_available"] == len(knowledge)


def test_groundedness_in_orchestrator_flow(monkeypatch):
    """End-to-end: groundedness runs in orchestrator flow."""
    from app.agent.orchestrator import run_turn

    monkeypatch.setattr(settings, "injection_guard_enabled", False)

    store = InMemoryStore()
    stub = _CallStub()

    payload = _payload("p_ground", "What is the mean of category A?")

    out = run_turn(payload, stub, store)

    components = out.get("components", {})
    assert "groundedness" in components, "Groundedness telemetry should be present"

    trace_data = components["groundedness"]
    # Either check ran (if passages available) or didn't (if no passages)
    assert "check_ran" in trace_data or "passages_available" in trace_data


def test_groundedness_control_no_op():
    """Control stance: groundedness is a no-op (no reasoner draft)."""
    from app.agent.orchestrator import run_turn

    store = InMemoryStore()
    stub = _CallStub()

    payload = _payload("p_control", "What is the mean?", stance="control")

    out = run_turn(payload, stub, store)

    # ✅ 不存储 components 变量，直接检查
    assert "groundedness" not in out.get("components", {})


def test_groundedness_trace_event_format():
    """Test that the groundedness trace event follows the expected format."""
    trace = groundedness.get_groundedness_trace(
        passage_count=3,
        citations_used=["passage_1", "passage_2"],
        ungrounded_fragments=["Claim not in passage"],
        all_grounded=False,
    )

    assert trace["passages_available"] == 3
    assert trace["citations_used"] == ["passage_1", "passage_2"]
    assert trace["ungrounded_count"] == 1
    assert trace["all_grounded"] is False
    # Content-free: no passage text
    assert "text" not in str(trace)
