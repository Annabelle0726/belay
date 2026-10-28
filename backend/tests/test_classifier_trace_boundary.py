# SPDX-License-Identifier: AGPL-3.0-only
"""Classifier evidence survives short circuits and authenticated trace filtering."""

import json
from types import SimpleNamespace

import pytest

from app.agent import injection_guard, run_turn
from app.auth import Identity
from app.config import settings
from app.store import InMemoryStore, make_event
from app.store.scoped import ScopedStore
from conftest import _CallStub, _payload


@pytest.fixture
def classifier(monkeypatch):
    monkeypatch.setattr(settings, "injection_guard_enabled", True)
    monkeypatch.setattr(settings, "injection_guard_model", "PRIVATE_MODEL_SENTINEL")
    monkeypatch.setattr(settings, "distress_routing_enabled", False)

    def install(status):
        def classify(**kwargs):
            if status == "error":
                raise OSError("PRIVATE_EXCEPTION_SENTINEL")
            return {
                "flagged": "false" if status == "malformed" else status == "flagged",
                "confidence": 0.2,
            }

        guard = injection_guard.InjectionGuard()
        guard._initialized = True
        guard._llm = None if status == "unavailable" else SimpleNamespace(json=classify)
        monkeypatch.setattr(injection_guard, "_guard_instance", guard)

    return install


def scoped():
    identity = Identity(
        "inst", "class", "gh:1", (("ds-foundations", "v1"),), "ds-foundations", "v1"
    )
    return ScopedStore(InMemoryStore(), identity)


@pytest.mark.parametrize("status", ["safe", "flagged", "malformed", "unavailable", "error"])
def test_authenticated_trace_retains_closed_classifier_outcomes(classifier, status):
    classifier(status)
    store = scoped()
    result = run_turn(
        _payload("gh:1", "PRIVATE_LEARNER_SENTINEL", stance="control"), _CallStub(), store
    )
    assert result["components"]["injection"]["status"] == status
    exported = store.export_jsonl("gh:1")
    row = json.loads(exported)
    evidence = row["payload"]["metrics"]["injection"]
    assert evidence["status"] == status
    assert evidence["triggered"] is (status == "flagged")
    assert evidence["score"] == (0.2 if status in {"safe", "flagged"} else 0.0)
    if status in {"malformed", "unavailable", "error"}:
        assert (
            evidence["error_category"]
            == {
                "malformed": "MALFORMED_JSON",
                "unavailable": "CLIENT_UNAVAILABLE",
                "error": "LLM_INFERENCE_ERROR",
            }[status]
        )
    for private in (
        "PRIVATE_LEARNER_SENTINEL",
        "PRIVATE_MODEL_SENTINEL",
        "PRIVATE_EXCEPTION_SENTINEL",
    ):
        assert private not in exported


@pytest.mark.parametrize("status", ["safe", "malformed", "unavailable", "error"])
@pytest.mark.parametrize("authenticated", [False, True])
def test_punctuation_followup_keeps_performed_classifier_evidence(
    classifier, status, authenticated
):
    classifier(status)
    store = scoped() if authenticated else InMemoryStore()
    llm = _CallStub()
    payload = _payload("gh:1", "?")
    payload["_reply_context"] = {"request_id": "old-reply", "text": "PRIVATE_QUOTE_SENTINEL"}
    result = run_turn(payload, llm, store)
    assert result["intervention"] == "clarify"
    assert llm.roles == []
    assert result["components"]["injection"]["status"] == status
    exported = store.export_jsonl("gh:1")
    row = json.loads(exported)
    evidence = row["payload"]["metrics" if authenticated else "telemetry"]["injection"]
    assert evidence["status"] == status
    assert "PRIVATE_QUOTE_SENTINEL" not in exported


@pytest.mark.parametrize("status", ["PRIVATE_STATUS_SENTINEL", ["safe"]])
def test_classifier_trace_does_not_admit_unvalidated_strings_or_scores(status):
    store = scoped()
    store.append_event(
        make_event(
            "gh:1",
            "ds-foundations",
            "study",
            "injection",
            {
                "status": status,
                "triggered": "PRIVATE_FLAG_SENTINEL",
                "score": float("nan"),
                "error_category": "PRIVATE_EXCEPTION_SENTINEL",
                "model": "PRIVATE_MODEL_SENTINEL",
            },
        )
    )
    exported = store.export_jsonl("gh:1")
    evidence = json.loads(exported)["payload"]["metrics"]["injection"]
    assert evidence["status"] == "unavailable"
    assert evidence["score"] is None
    assert "triggered" not in evidence
    assert "error_category" not in evidence
    assert "PRIVATE_" not in exported
