"""
Deployability tests (6c): the preflight doctor + the minimal /quad/v1 embed turn
against the _skeleton pack. No network (control stance; provider probe skipped).
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.quad import build_router
from app.packs._skeleton import SkeletonPack
from app.preflight import check_config, check_store, run
from app.store import ConsentRouter, InMemoryStore

# ── preflight doctor ──────────────────────────────────────────────────────────

def test_preflight_config_passes():
    ok, msg = check_config()
    assert ok, msg


def test_preflight_store_reachable():
    ok, msg = check_store()
    assert ok, msg


def test_preflight_run_structure():
    # Without the provider probe: config + store only.
    names = [n for n, _ in run(probe_provider=False)]
    assert names == ["config", "store"]
    # With the probe: provider reachability is also checked.
    assert "provider" in [n for n, _ in run(probe_provider=True)]


def test_preflight_provider_check_handles_unreachable():
    from app.preflight import check_provider
    ok, msg = check_provider(timeout=0.2)   # nothing guaranteed up → must not raise
    assert isinstance(ok, bool) and isinstance(msg, str)


# ── embed demo: one /quad/v1 turn against the _skeleton pack ──────────────────

def test_embed_demo_turn_against_skeleton(monkeypatch):
    # The embed demo runs against the _skeleton pack — the server is launched with
    # TUTOR_PACK=_skeleton so the active pack drives the turn (as the page documents).
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    from app.core.domain import get_active_pack
    assert isinstance(get_active_pack(), SkeletonPack)

    app = FastAPI()
    app.include_router(build_router(ConsentRouter(InMemoryStore()), get_active_pack(),
                                    lambda: None))   # control stance: no LLM
    out = TestClient(app).post("/quad/v1/turn", json={
        "pseudo_id": "gh:12345", "exercise_id": "echo-1",
        "stance": "control", "source": "print('ok')",
    })
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["components"]["pack"] == "_skeleton"
    assert "intervention" in body and "message" in body


def test_embed_demo_page_targets_quad_and_skeleton():
    path = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "embed-demo.html"))
    assert os.path.exists(path), path
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    assert "/quad/v1/turn" in html
    assert "echo-1" in html         # the _skeleton pack exercise
    assert "gh:12345" in html       # pseudonymous identity only
