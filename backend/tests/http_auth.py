# SPDX-License-Identifier: AGPL-3.0-only
"""Hermetic signed credentials used by HTTP behavior tests; no dependency overrides."""

from __future__ import annotations

import json
import time

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import settings

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = _PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
)
ISSUER = "https://identity.test.invalid"
AUDIENCE = "belay-tests"


def token(subject="gh:12345", **claims):
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "iat": now, "exp": now + 300}
    payload.update(claims)
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")


def configure(monkeypatch, tmp_path, authorization):
    key_file = tmp_path / "identity.pub"
    auth_file = tmp_path / "authorization.json"
    key_file.write_bytes(PUBLIC_KEY)
    auth_file.write_text(json.dumps(authorization), encoding="utf-8")
    for name, value in {
        "belay_env": "test",
        "auth_issuer": ISSUER,
        "auth_audience": AUDIENCE,
        "auth_public_key_file": str(key_file),
        "auth_authorization_file": str(auth_file),
    }.items():
        monkeypatch.setattr(settings, name, value)
    return auth_file


def authenticated_client(app, learner="gh:12345"):
    return TestClient(app, headers={"Authorization": "Bearer " + token(learner)})
