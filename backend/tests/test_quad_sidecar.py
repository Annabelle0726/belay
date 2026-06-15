"""
Quad tutor-seam sidecar tests (/quad/v1): the four routes, the PII boundary, and
the grades firewall. Uses an InMemoryStore-backed wiring + control stance so no
network or DB is touched.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.domain import get_active_pack
from app.integrations.quad import build_router
from app.integrations.quad.pii import PIIRejected, assert_no_pii, pii_reason
from app.store import ConsentRouter, InMemoryStore


def _client():
    cr = ConsentRouter(InMemoryStore())   # ephemeral; no DB writes

    def _no_llm():
        class _NoLLM:  # control stance never calls .json
            def json(self, **_k):
                raise AssertionError("control stance must not call the LLM")
        return _NoLLM()

    app = FastAPI()
    app.include_router(build_router(cr, get_active_pack(), _no_llm))
    return TestClient(app)


# ── the four routes ───────────────────────────────────────────────────────────

def test_health():
    r = _client().get("/quad/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["protocol"] == "quad/v1"


def test_capabilities_declares_identity_and_grades_firewall():
    body = _client().get("/quad/v1/capabilities").json()
    assert body["protocol"] == "quad/v1"
    assert body["identity"]["scheme"] == "pseudonymous"
    assert body["grades"]["writes"] is False
    assert body["grades"]["mode"] == "read-only"
    assert body["license"] == "Apache-2.0"
    assert "POST /quad/v1/turn" in body["routes"]


def test_turn_runs_control_stance():
    """A control-stance turn runs end to end with a pseudonymous id only."""
    r = _client().post("/quad/v1/turn", json={
        "pseudo_id": "gh:12345", "exercise_id": "ds-foundations",
        "stance": "control", "source": "import pandas as pd",
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["components"]["stance"] == "control"
    assert "message" in out


def test_events_acks_clean_payload():
    r = _client().post("/quad/v1/events", json={"type": "workspace.updated", "pseudo_id": "gh:7"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ── PII boundary (privacy is the hard constraint) ─────────────────────────────

def test_pii_rejected_email():
    r = _client().post("/quad/v1/turn", json={
        "pseudo_id": "gh:12345", "exercise_id": "ds-foundations", "stance": "control",
        "contact": "jane.doe@university.edu",
    })
    assert r.status_code == 422
    assert "PII rejected" in r.json()["detail"]


def test_pii_rejected_name_field():
    r = _client().post("/quad/v1/turn", json={
        "pseudo_id": "gh:12345", "exercise_id": "ds-foundations", "stance": "control",
        "student_name": "Jane Doe",
    })
    assert r.status_code == 422
    assert "PII rejected" in r.json()["detail"]


def test_pii_rejected_sis_id():
    r = _client().post("/quad/v1/turn", json={
        "pseudo_id": "gh:12345", "exercise_id": "ds-foundations", "stance": "control",
        "sis_id": "A00123456",
    })
    assert r.status_code == 422


def test_non_pseudonymous_id_rejected():
    r = _client().post("/quad/v1/turn", json={
        "pseudo_id": "jane.doe", "exercise_id": "ds-foundations", "stance": "control",
    })
    assert r.status_code == 422


def test_pii_helper_unit():
    assert pii_reason({"pseudo_id": "gh:12345"}) is None
    assert pii_reason({"pseudo_id": "gh:1", "email": "a@b.co"}) is not None
    assert pii_reason({"pseudo_id": "not-a-pseudo-id"}) is not None
    # student code may legitimately contain an '@' — `source` is not scanned.
    assert pii_reason({"pseudo_id": "gh:1", "source": "x = '@decorator'"}) is None
    try:
        assert_no_pii({"pseudo_id": "gh:1", "full_name": "x"})
        raise AssertionError("expected PIIRejected")
    except PIIRejected:
        pass


# ── grades firewall: gradingspec_result is read-only; no write path ───────────

def test_gradingspec_result_is_read_only_context():
    """A gradingspec_result is accepted as turn context and produces a normal
    tutor turn — with NO grade-write field in the response and no write route."""
    client = _client()
    out = client.post("/quad/v1/turn", json={
        "pseudo_id": "gh:12345", "exercise_id": "ds-foundations", "stance": "control",
        "gradingspec_result": {"ok": True, "goalMet": False, "metric": 0.4,
                               "pack": {"id": "datascience", "summary": "r2=0.40"}},
    }).json()
    # The turn response is the tutor turn only — it never writes/echoes a grade.
    for forbidden in ("grade", "grade_write", "gradingspec_write", "grading_write", "score_write"):
        assert forbidden not in out


def test_no_grade_write_route_exists():
    """The sidecar exposes exactly health/capabilities/turn/events — no grade-write
    route exists (the tutor never writes grades)."""
    api = build_router(ConsentRouter(InMemoryStore()), get_active_pack(), lambda: None)
    paths = {(r.path, tuple(sorted(set(r.methods) - {"HEAD", "OPTIONS"})))
             for r in api.routes}
    assert paths == {
        ("/quad/v1/health", ("GET",)),
        ("/quad/v1/capabilities", ("GET",)),
        ("/quad/v1/turn", ("POST",)),
        ("/quad/v1/events", ("POST",)),
    }


def test_sidecar_source_has_no_grade_write_calls():
    """Static guard: the sidecar source contains no grade-writing surface."""
    import os
    import app.integrations.quad as quad_pkg
    quad_dir = os.path.dirname(quad_pkg.__file__)
    forbidden = ("write_grade", "post_grade", "put_grade", "set_grade",
                 "gradebook", "submit_grade")
    for fn in os.listdir(quad_dir):
        if fn.endswith(".py"):
            with open(os.path.join(quad_dir, fn), encoding="utf-8") as fh:
                text = fh.read().lower()
            for tok in forbidden:
                assert tok not in text, f"{fn}: forbidden grade-write token {tok!r}"
