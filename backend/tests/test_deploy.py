# SPDX-License-Identifier: AGPL-3.0-only
"""
Deployability tests: preflight, the legacy /quad/v1 turn contract, and the
controlled embed page against the _skeleton pack. No paid model calls.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from app.integrations.quad import build_router
from app.packs._skeleton import SkeletonPack
from app.preflight import check_config, check_store, run
from app.store import ConsentRouter, InMemoryStore
from tests.http_auth import authenticated_client

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

    ok, msg = check_provider(timeout=0.2)  # nothing guaranteed up → must not raise
    assert isinstance(ok, bool) and isinstance(msg, str)


# ── embed demo: one /quad/v1 turn against the _skeleton pack ──────────────────


def test_embed_demo_turn_against_skeleton(monkeypatch):
    # The embed demo runs against the _skeleton pack — the server is launched with
    # TUTOR_PACK=_skeleton so the active pack drives the turn (as the page documents).
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    from app.core.registry import get_active_pack

    assert isinstance(get_active_pack(), SkeletonPack)

    app = FastAPI()
    app.include_router(
        build_router(ConsentRouter(InMemoryStore()), get_active_pack(), lambda: None)
    )  # control stance: no LLM
    out = authenticated_client(app, "gh:12345").post(
        "/quad/v1/turn",
        json={
            "pseudo_id": "gh:12345",
            "exercise_id": "echo-1",
            "stance": "control",
            "source": "print('ok')",
        },
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert "message" in body and body["glass_box"]["approach"]
    assert "components" not in body and "intervention" not in body


def test_embed_demo_page_targets_controlled_quad_jobs_and_skeleton():
    path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "embed-demo.html")
    )
    assert os.path.exists(path), path
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    assert '<script src="ask-jobs.js"></script>' in html
    assert "askJobs.ask(base, '/quad/v1/jobs'" in html
    assert "askJobs.recover(base,'/quad/v1/jobs'" in html
    assert "askJobs.acknowledge(data)" in html
    assert "/quad/v1/turn" not in html
    assert "echo-1" in html  # the _skeleton pack exercise
    assert "gh:12345" in html  # pseudonymous identity only
