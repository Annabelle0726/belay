# SPDX-License-Identifier: AGPL-3.0-only
"""Normalize configured origins; opaque null origins require an explicit opt-in."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.config import Settings


def configuration(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", value)
    return Settings()


def preflight(settings, origin):
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return TestClient(app).options(
        "/api/sol/turn",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_default_rejects_null_and_keeps_named_dev_origins(monkeypatch):
    settings = configuration(monkeypatch, None)
    assert "null" not in settings.cors_origins
    assert "http://localhost:5173" in settings.cors_origins
    assert "http://localhost:3000" in settings.cors_origins
    response = preflight(settings, "null")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "value,expected",
    [
        (
            " http://localhost:5173 , ,http://127.0.0.1:5177, ",
            ["http://localhost:5173", "http://127.0.0.1:5177"],
        ),
        (" , , ", []),
        ("", []),
        (" null, http://localhost:5173 ", ["null", "http://localhost:5173"]),
    ],
)
def test_configured_entries_are_trimmed_without_empty_fallback(monkeypatch, value, expected):
    assert configuration(monkeypatch, value).cors_origins == expected


@pytest.mark.parametrize(
    "configured,origin,allowed",
    [
        ("null,http://localhost:5173", "null", True),
        ("http://127.0.0.1:5177", "http://127.0.0.1:5177", True),
        ("http://127.0.0.1:5177", "http://localhost:5177", False),
        ("http://localhost:5173", "http://unlisted.invalid", False),
        ("", "null", False),
    ],
)
def test_preflight_obeys_exact_allowlist(monkeypatch, configured, origin, allowed):
    response = preflight(configuration(monkeypatch, configured), origin)
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)
