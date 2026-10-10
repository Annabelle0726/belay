# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP error wiring only; these synthetic requests do not prove authentication."""

import pytest
from fastapi import FastAPI

from app.config import settings
from app.controls.contracts import ControlError
from app.core.registry import get_active_pack
from app.integrations.quad import build_router
from app.store import ConsentRouter, InMemoryStore
from tests.http_auth import authenticated_client


@pytest.fixture(autouse=True)
def active_pack(monkeypatch):
    # Other identity tests intentionally import main with the skeleton pack.
    from app import main
    from app.packs.datascience import DataSciencePack

    monkeypatch.setattr(main, "_pack", DataSciencePack())
    app = FastAPI()
    app.router.routes.extend(
        r for r in main.app.routes if getattr(r, "path", "").startswith("/api/")
    )
    app.add_exception_handler(ControlError, main.control_error)
    app.add_middleware(
        main.CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.include_router(build_router(ConsentRouter(InMemoryStore()), main._pack, main._llm))
    return app


@pytest.mark.parametrize(
    "path,payload,target",
    [
        (
            "/api/run",
            {"participant_id": "gh:12345", "exercise_id": "ds-foundations", "source": "pass"},
            "run",
        ),
        ("/api/sol/turn", {"participant_id": "gh:12345", "exercise_id": "ds-foundations"}, "sol"),
        ("/quad/v1/turn", {"pseudo_id": "gh:12345", "exercise_id": "ds-foundations"}, "quad"),
    ],
)
def test_http_preserves_retry_after_for_cross_origin_clients(
    monkeypatch, path, payload, target, active_pack
):
    import app.integrations.quad.router as quad
    import app.main as main

    monkeypatch.setattr(settings, "controls_mode", "development_bypass")
    monkeypatch.setattr(main._llm, "_inst", object(), raising=False)

    def deny(*args):
        raise ControlError("rate_limited", retry_after=3)

    if target == "run":
        monkeypatch.setattr(main._pack, "run", deny)
    else:
        monkeypatch.setattr(main if target == "sol" else quad, "run_turn", deny)
    with authenticated_client(active_pack) as client:
        response = client.post(path, json=payload, headers={"Origin": settings.cors_origins[0]})
    assert response.status_code == 429
    assert response.json() == {"detail": {"code": "rate_limited"}}
    assert response.headers["Retry-After"] == "3"
    assert "retry-after" in response.headers["Access-Control-Expose-Headers"].lower()


@pytest.mark.parametrize("quad_surface", [False, True])
def test_http_unknown_failure_hides_provider_diagnostics(monkeypatch, quad_surface, active_pack):
    import app.integrations.quad.router as quad
    import app.main as main

    monkeypatch.setattr(settings, "controls_mode", "development_bypass")
    monkeypatch.setattr(main._llm, "_inst", object(), raising=False)

    def fail(*args):
        raise TimeoutError("PRIVATE provider response/credential")

    monkeypatch.setattr(quad if quad_surface else main, "run_turn", fail)
    path = "/quad/v1/turn" if quad_surface else "/api/sol/turn"
    payload = {"exercise_id": "ds-foundations"}
    payload["pseudo_id" if quad_surface else "participant_id"] = "gh:12345"
    with authenticated_client(active_pack) as client:
        response = client.post(path, json=payload)
    assert response.status_code == 502
    assert response.json() == {"detail": {"code": "execution_unknown"}}
    assert "PRIVATE" not in response.text


def test_embedded_quad_router_keeps_retry_headers_without_main_handler(monkeypatch):
    import app.integrations.quad.router as quad

    def deny():
        raise ControlError("coordinator_unavailable", 503, retry_after=2)

    monkeypatch.setattr(quad, "control_context", deny)
    app = FastAPI()
    app.include_router(
        build_router(ConsentRouter(InMemoryStore()), get_active_pack(), lambda: None)
    )
    with authenticated_client(app) as client:
        response = client.post("/quad/v1/turn", json={})
    assert response.status_code == 503 and response.headers["Retry-After"] == "2"
