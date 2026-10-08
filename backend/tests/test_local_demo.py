# SPDX-License-Identifier: AGPL-3.0-only
"""Local host smoke: real offline RSA verification, no model or external issuer."""

from __future__ import annotations

import json
import threading
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.packs._skeleton.pack import SkeletonPack
from scripts.local_demo import (
    AUDIENCE,
    ISSUER,
    TOKEN_PATH,
    DemoHandler,
    DemoIdentity,
    bootstrap,
)


@pytest.fixture
def local_host(tmp_path):
    identity = DemoIdentity(tmp_path, SkeletonPack())
    handler = partial(DemoHandler, identity=identity, backend_port=8001)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield identity, server.server_address[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def get(port, path, headers=None, method="GET"):
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_page_bootstrap_without_embedded_token(local_host):
    _, port = local_host
    for page in ("dev-client.html", "widget.html", "embed-demo.html"):
        status, headers, body = get(port, "/" + page)
        text = body.decode()
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert text.index("window.BELAY_AUTH_ORIGIN") < text.index('<script src="auth-client.js">')
        assert 'value="http://127.0.0.1:8001"' in text
        assert "eyJ" not in text
        assert "X-Belay-Local-Demo" in text
        assert headers["Content-Security-Policy"] == "frame-ancestors 'none'"


@pytest.mark.parametrize(
    "headers,path",
    [
        ({}, TOKEN_PATH),
        ({"X-Belay-Local-Demo": "1", "Host": "attacker.invalid"}, TOKEN_PATH),
        ({"X-Belay-Local-Demo": "1", "Origin": "https://attacker.invalid"}, TOKEN_PATH),
        ({"X-Belay-Local-Demo": "1", "Sec-Fetch-Site": "cross-site"}, TOKEN_PATH),
        ({"X-Belay-Local-Demo": "1"}, TOKEN_PATH + "?token=unused"),
    ],
)
def test_token_host_rejects_cross_origin_and_bare_requests(local_host, headers, path):
    _, port = local_host
    assert get(port, path, headers)[0] == 403


def test_token_is_short_lived_and_private_key_not_on_disk(local_host, tmp_path):
    identity, port = local_host
    status, headers, body = get(port, TOKEN_PATH, {"X-Belay-Local-Demo": "1"})
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers
    signed = json.loads(body)["access_token"]
    claims = jwt.decode(
        signed,
        identity.public_key_file.read_text(),
        algorithms=["RS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    assert claims["exp"] - claims["iat"] == 300
    assert {file.name for file in tmp_path.iterdir()} == {"identity.pub", "authorization.json"}
    assert get(port, TOKEN_PATH, method="HEAD")[0] == 403


def test_local_credentials_use_normal_backend_authorization(local_host, monkeypatch):
    identity, port = local_host
    for name, value in {
        "belay_env": "local",
        "auth_issuer": ISSUER,
        "auth_audience": AUDIENCE,
        "auth_public_key_file": str(identity.public_key_file),
        "auth_authorization_file": str(identity.authorization_file),
        "store_backend": "memory",
    }.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    from app import main

    monkeypatch.setattr(main, "_pack", SkeletonPack())
    client = TestClient(main.app)
    signed = json.loads(get(port, TOKEN_PATH, {"X-Belay-Local-Demo": "1"})[2])["access_token"]
    headers = {"Authorization": "Bearer " + signed}
    assert client.get("/api/curriculum").status_code == 401
    assert client.get("/api/curriculum", headers=headers).status_code == 200
    assert client.get("/api/goals/gh:999", headers=headers).status_code == 404
    assert (
        client.get("/api/curriculum", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )


def test_launcher_environment_explicit_local_and_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("BELAY_ENV", "production")
    monkeypatch.setenv("STORE_BACKEND", "sql")
    identity = DemoIdentity(tmp_path, SkeletonPack())
    env = identity.backend_environment(5174, "_skeleton")
    assert env["BELAY_ENV"] == "local" and env["STORE_BACKEND"] == "memory"
    assert env["TUTOR_PACK"] == "_skeleton"
    assert env["CORS_ORIGINS"] == "http://127.0.0.1:5174,http://localhost:5174"
    assert "private" not in " ".join(env[k] for k in env if k.startswith("AUTH_"))
    assert TOKEN_PATH in bootstrap(8001)
