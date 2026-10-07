# SPDX-License-Identifier: AGPL-3.0-only
"""Authentication and isolation at both real HTTP edges; RSA keys and models are offline."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import replace

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import Identity
from app.config import settings
from app.integrations.quad import build_router
from app.packs._skeleton.pack import SkeletonPack
from app.store import ConsentRouter, InMemoryStore, SqlStore, make_event
from app.store.models import Base, Participant
from app.store.scoped import ScopedStore, register, scoped_store
from tests.http_auth import configure, token


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    def member(institution="inst-a", class_id="class-a", learner="gh:1", assignments=None):
        return {
            "institution_id": institution,
            "class_id": class_id,
            "learner_id": learner,
            "assignments": {"echo-1": "v1"} if assignments is None else assignments,
        }

    authorization = {
        "exercise_versions": {"echo-1": "v1"},
        "subjects": {
            "subject-a": [member()],
            "subject-b": [member(learner="gh:2")],
            "subject-class": [member(class_id="class-b")],
            "subject-inst": [member(institution="inst-b")],
            "subject-no-grant": [member(assignments={})],
            "subject-multi": [member(), member(class_id="class-b")],
        },
    }
    auth_file = configure(monkeypatch, tmp_path, authorization)
    monkeypatch.setattr(settings, "store_backend", "memory")
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    from app import main

    router = ConsentRouter(InMemoryStore())
    pack = SkeletonPack()
    calls = []

    def run(source, exercise):
        calls.append((source, exercise["id"]))
        return {"ok": True, "goalMet": False, "metric": 0.2, "pack": {"stdout": source}}

    monkeypatch.setattr(pack, "run", run)
    monkeypatch.setattr(main, "_router", router)
    monkeypatch.setattr(main, "_pack", pack)

    def llm_factory():
        calls.append(("llm", None))
        return None

    monkeypatch.setattr(main, "_llm", llm_factory)
    app = FastAPI()
    # Mount the actual /api routes, with the actual auth dependency, over fresh wiring.
    app.router.routes.extend(
        r
        for r in main.app.routes
        if getattr(r, "path", "").startswith("/api/") or getattr(r, "path", "") == "/healthz"
    )
    app.include_router(build_router(router, pack, llm_factory))
    return TestClient(app), router, calls, auth_file, authorization


def headers(subject="subject-a", **selectors):
    return {"Authorization": "Bearer " + token(subject), **selectors}


ENDPOINTS = [
    ("GET", "/api/curriculum", None),
    ("POST", "/api/participant", {"anon_code": "gh:1", "consent": True}),
    ("POST", "/api/run", {"participant_id": "gh:1", "exercise_id": "echo-1", "source": "code"}),
    (
        "POST",
        "/api/sol/turn",
        {"participant_id": "gh:1", "exercise_id": "echo-1", "stance": "control"},
    ),
    ("POST", "/api/goals", {"participant_id": "gh:1", "text": "go slowly"}),
    ("GET", "/api/goals/gh:1", None),
    ("POST", "/api/reflection", {"participant_id": "gh:1", "text": "I understand"}),
    (
        "POST",
        "/api/overlay",
        {"participant_id": "gh:1", "overlay": {"persona": {"tone": "direct"}}},
    ),
    ("GET", "/api/session/gh:1/events.jsonl", None),
    ("POST", "/quad/v1/turn", {"pseudo_id": "gh:1", "exercise_id": "echo-1", "stance": "control"}),
    ("POST", "/quad/v1/goals", {"pseudo_id": "gh:1", "text": "go slowly"}),
    ("POST", "/quad/v1/reflection", {"pseudo_id": "gh:1", "text": "I understand"}),
    ("POST", "/quad/v1/overlay", {"pseudo_id": "gh:1", "overlay": {"persona": {"tone": "direct"}}}),
    (
        "POST",
        "/quad/v1/events",
        {"pseudo_id": "gh:1", "exercise_id": "echo-1", "type": "workspace.updated"},
    ),
]


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
@pytest.mark.parametrize("credential", ["missing", "invalid", "expired"])
def test_every_student_endpoint_requires_valid_credentials(
    boundary, method, path, body, credential
):
    client, router, calls, _, _ = boundary
    auth = (
        {}
        if credential == "missing"
        else {
            "Authorization": "Bearer "
            + (
                "invalid"
                if credential == "invalid"
                else token("subject-a", iat=int(time.time()) - 100, exp=int(time.time()) - 1)
            )
        }
    )
    response = client.request(method, path, json=body, headers=auth)
    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"
    assert calls == [] and router._consent_cache == {} and router.durable._events == []


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://attacker.invalid"},
        {"aud": "other-service"},
        {"nbf": int(time.time()) + 600},
        {"iat": int(time.time()) + 600},
        {"exp": None},
        {"sub": None},
        {"iat": True},
        {"exp": "9999999999"},
    ],
)
def test_invalid_claims(boundary, claims):
    client, _, calls, _, _ = boundary
    response = client.post(
        "/api/run",
        json=ENDPOINTS[2][2],
        headers={"Authorization": "Bearer " + token("subject-a", **claims)},
    )
    assert response.status_code == 401
    assert calls == []


@pytest.mark.parametrize("claim", ["iss", "aud", "exp", "iat", "sub"])
def test_required_claims(boundary, claim):
    from tests.http_auth import _PRIVATE_KEY

    claims = jwt.decode(token("subject-a"), options={"verify_signature": False})
    del claims[claim]
    signed = jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256")
    assert (
        boundary[0]
        .get("/api/goals/gh:1", headers={"Authorization": "Bearer " + signed})
        .status_code
        == 401
    )


def test_signature_and_algorithm_pinning(boundary):
    from cryptography.hazmat.primitives.asymmetric import rsa

    claims = jwt.decode(token("subject-a"), options={"verify_signature": False})
    forged = [
        jwt.encode(
            claims,
            rsa.generate_private_key(public_exponent=65537, key_size=2048),
            algorithm="RS256",
        ),
        jwt.encode(claims, "attacker-secret-01234567890123456789", algorithm="HS256"),
        jwt.encode(claims, key="", algorithm="none"),
    ]
    for signed in forged:
        assert (
            boundary[0]
            .post("/api/run", json=ENDPOINTS[2][2], headers={"Authorization": "Bearer " + signed})
            .status_code
            == 401
        )
    assert boundary[2] == []


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_legal_requests_on_both_surfaces(boundary, method, path, body):
    assert boundary[0].request(method, path, json=body, headers=headers()).status_code == 200


@pytest.mark.parametrize("method,path,body", [e for e in ENDPOINTS if e[0] == "POST"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("participant_id", "gh:2"),
        ("pseudo_id", "gh:2"),
        ("learner_id", "gh:2"),
        ("class_id", "class-b"),
        ("institution_id", "inst-b"),
    ],
)
def test_body_cannot_assign_identity(boundary, method, path, body, field, value):
    response = boundary[0].request(method, path, json={**body, field: value}, headers=headers())
    assert response.status_code == 404 and response.json() == {"detail": "resource unavailable"}
    assert boundary[1]._consent_cache == {} and boundary[2] == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/goals/gh:2",
        "/api/goals/gh:999",
        "/api/session/gh:2/events.jsonl",
        "/api/session/gh:999/events.jsonl",
    ],
)
def test_other_learner_and_nonexistent_are_indistinguishable(boundary, path):
    r = boundary[0].get(path, headers=headers())
    assert r.status_code == 404 and r.json() == {"detail": "resource unavailable"}


@pytest.mark.parametrize("subject", ["subject-inst", "subject-class", "subject-b"])
def test_state_registration_and_export_are_partitioned(boundary, subject):
    client, router, _, _, _ = boundary
    own = headers()
    client.post("/api/participant", json={"anon_code": "gh:1", "consent": True}, headers=own)
    client.post("/api/goals", json={"participant_id": "gh:1", "text": "private goal"}, headers=own)
    client.post(
        "/api/reflection",
        json={"participant_id": "gh:1", "text": "private reflection"},
        headers=own,
    )
    client.post(
        "/api/overlay",
        json={"participant_id": "gh:1", "overlay": {"persona": {"tone": "direct"}}},
        headers=own,
    )
    client.post("/api/run", json=ENDPOINTS[2][2], headers=own)
    other = headers(subject)
    pid = "gh:2" if subject == "subject-b" else "gh:1"
    assert client.get(f"/api/goals/{pid}", headers=other).json()["goals"] is None
    assert client.get(f"/api/session/{pid}/events.jsonl", headers=other).text == ""
    assert (
        client.post(
            "/quad/v1/goals",
            json={"pseudo_id": pid, "text": "other goal", "consent": True},
            headers=other,
        ).status_code
        == 200
    )
    assert client.get("/api/goals/gh:1", headers=own).json()["goals"]["text"] == "private goal"
    own_id = Identity("inst-a", "class-a", "gh:1", (("echo-1", "v1"),), "echo-1", "v1")
    other_id = Identity(
        "inst-b" if subject == "subject-inst" else "inst-a",
        "class-b" if subject == "subject-class" else "class-a",
        pid,
        (("echo-1", "v1"),),
        "echo-1",
        "v1",
    )
    assert scoped_store(router, other_id).get_learner_state(pid)["reflections"] == []
    assert scoped_store(router, other_id).get_learner_state(pid)["overlay"] is None
    assert scoped_store(router, other_id).attempts(pid, "echo-1") == 0
    assert scoped_store(router, own_id).attempts("gh:1", "echo-1") == 1
    assert len(router._consent_cache) == 2


def test_selectors_only_select_authorized_membership(boundary):
    client = boundary[0]
    assert (
        client.get(
            "/api/goals/gh:1",
            headers=headers(**{"X-Belay-Institution": "inst-b", "X-Belay-Class": "class-a"}),
        ).status_code
        == 404
    )
    assert client.get("/api/goals/gh:1", headers=headers("subject-multi")).status_code == 404
    selected = headers(
        "subject-multi", **{"X-Belay-Institution": "inst-a", "X-Belay-Class": "class-b"}
    )
    assert client.get("/api/goals/gh:1", headers=selected).status_code == 200
    assert client.get("/api/goals/gh:1", headers=headers("unknown-subject")).status_code == 404


@pytest.mark.parametrize("path", ["/api/run", "/api/sol/turn", "/quad/v1/turn", "/quad/v1/events"])
def test_assignment_version_authorization_precedes_execution(boundary, path):
    client, _, calls, _, _ = boundary
    body = {
        "participant_id": "gh:1",
        "pseudo_id": "gh:1",
        "exercise_id": "echo-1",
        "source": "code",
        "stance": "control",
    }
    for auth, update in [
        (headers("subject-no-grant"), {}),
        (headers(), {"exercise_version": "v0"}),
        (headers(), {"exercise_id": "missing"}),
        (headers(), {"exercise_id": None}),
    ]:
        assert client.post(path, json={**body, **update}, headers=auth).status_code == 404
    assert calls == []


def test_version_events_and_attempts_do_not_bleed_and_revocation_is_immediate(boundary):
    client, router, _, file, authorization = boundary
    client.post("/api/participant", json={"anon_code": "gh:1", "consent": True}, headers=headers())
    client.post(
        "/api/goals", json={"participant_id": "gh:1", "text": "class goal"}, headers=headers()
    )
    client.post("/api/run", json={**ENDPOINTS[2][2], "exercise_version": "v1"}, headers=headers())
    authorization["exercise_versions"]["echo-1"] = "v2"
    authorization["subjects"]["subject-a"][0]["assignments"]["echo-1"] = "v2"
    file.write_text(json.dumps(authorization))
    assert (
        client.post(
            "/api/run", json={**ENDPOINTS[2][2], "exercise_version": "v1"}, headers=headers()
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/run", json={**ENDPOINTS[2][2], "exercise_version": "v2"}, headers=headers()
        ).status_code
        == 200
    )
    identity = Identity("inst-a", "class-a", "gh:1", (("echo-1", "v2"),), "echo-1", "v2")
    assert scoped_store(router, identity).attempts("gh:1", "echo-1") == 1
    assert scoped_store(router, identity).get_learner_state("gh:1")["goals"]["text"] == "class goal"
    exported = client.get("/api/session/gh:1/events.jsonl", headers=headers()).text
    assert '"v1"' not in exported and '"v2"' in exported
    del authorization["subjects"]["subject-a"]
    file.write_text(json.dumps(authorization))
    assert client.get("/api/session/gh:1/events.jsonl", headers=headers()).status_code == 404


def test_legacy_records_unavailable_and_exports_content_free(boundary):
    client, router, _, _, _ = boundary
    router.durable.save_learner_state("gh:1", {"goals": {"text": "legacy secret"}})
    router.durable.append_event(
        make_event("gh:1", "echo-1", "study", "run", {"source": "legacy secret"})
    )
    assert client.get("/api/goals/gh:1", headers=headers()).json()["goals"] is None
    assert client.get("/api/session/gh:1/events.jsonl", headers=headers()).text == ""
    client.post("/api/participant", json={"anon_code": "gh:1", "consent": True}, headers=headers())
    client.post(
        "/api/goals", json={"participant_id": "gh:1", "text": "verbatim secret"}, headers=headers()
    )
    client.post("/api/run", json={**ENDPOINTS[2][2], "source": "verbatim code"}, headers=headers())
    exported = client.get("/api/session/gh:1/events.jsonl", headers=headers()).text
    assert "secret" not in exported and "verbatim" not in exported and "stdout" not in exported
    rows = [json.loads(line) for line in exported.splitlines()]
    assert len(rows) == 2
    assert all(
        set(row)
        == {
            "participant_id",
            "exercise_id",
            "ts",
            "mode",
            "event_type",
            "stance",
            "payload",
            "note",
        }
        for row in rows
    )


def test_consent_is_class_scoped_and_nonconsent_stays_ephemeral(boundary):
    client, router, _, _, _ = boundary
    for subject, consent in [("subject-a", True), ("subject-class", False)]:
        assert (
            client.post(
                "/api/participant",
                json={"anon_code": "gh:1", "consent": consent},
                headers=headers(subject),
            ).status_code
            == 200
        )
        assert (
            client.post("/api/run", json=ENDPOINTS[2][2], headers=headers(subject)).status_code
            == 200
        )
    assert client.get("/api/session/gh:1/events.jsonl", headers=headers()).text
    assert client.get("/api/session/gh:1/events.jsonl", headers=headers("subject-class")).text == ""
    assert len(router._ephemeral) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("auth_issuer", ""),
        ("auth_audience", ""),
        ("auth_public_key_file", "missing"),
        ("auth_authorization_file", "missing"),
        ("belay_env", "invalid"),
    ],
)
def test_missing_config_fails_closed_but_health_is_public(boundary, monkeypatch, field, value):
    monkeypatch.setattr(settings, field, value)
    assert boundary[0].post("/api/run", json=ENDPOINTS[2][2], headers=headers()).status_code == 503
    assert boundary[0].get("/healthz").status_code == 200
    assert boundary[0].get("/quad/v1/health").status_code == 200


def test_production_does_not_allow_local_issuer(boundary, monkeypatch):
    monkeypatch.setattr(settings, "belay_env", "production")
    monkeypatch.setattr(settings, "auth_issuer", "http://localhost:8080")
    assert boundary[0].get("/api/goals/gh:1", headers=headers()).status_code == 503


def test_untrusted_claims_do_not_grant_access(boundary):
    signed = token(
        "subject-a",
        institution_id="inst-b",
        class_id="class-b",
        learner_id="gh:2",
        assignments={"missing": "v1"},
    )
    auth = {"Authorization": "Bearer " + signed}
    assert boundary[0].get("/api/goals/gh:2", headers=auth).status_code == 404
    assert (
        boundary[0]
        .post("/api/run", json={**ENDPOINTS[2][2], "exercise_id": "missing"}, headers=auth)
        .status_code
        == 404
    )
    assert boundary[0].get("/api/goals/gh:1", headers=auth).status_code == 200


@pytest.mark.parametrize("database_backend", ["sqlite", "configured"])
def test_sql_scoping_registration_repeatable_and_consent_not_stale(
    tmp_path, monkeypatch, database_backend
):
    from app.store import db

    engine = (
        create_engine("sqlite:///" + str(tmp_path / "scope.db"))
        if database_backend == "sqlite"
        else db.engine
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", sessions)
    monkeypatch.setattr(db, "engine", engine)
    router = ConsentRouter(SqlStore())
    identity = Identity(
        "inst-" + uuid.uuid4().hex, "class-a", "gh:1", (("echo-1", "v1"),), "echo-1", "v1"
    )
    other = replace(identity, class_id="class-b")
    for _ in range(2):
        register(router, identity, True)
        register(router, other, False)
    scoped_store(router, identity).save_learner_state("gh:1", {"goals": {"text": "private goal"}})
    scoped_store(router, identity).append_event(
        make_event("gh:1", "echo-1", "study", "run", {"result": {"ok": True}})
    )
    assert scoped_store(router, other).get_learner_state("gh:1")["goals"] is None
    assert ScopedStore(router.durable, other).export_jsonl("gh:1") == ""
    assert scoped_store(router, identity).attempts("gh:1", "echo-1") == 1
    with sessions() as session:
        assert (
            len(
                session.execute(
                    select(Participant).where(
                        Participant.id.in_([identity.storage_id, other.storage_id])
                    )
                )
                .scalars()
                .all()
            )
            == 2
        )
    second_worker = ConsentRouter(SqlStore())
    register(second_worker, identity, False)
    assert isinstance(router.store_for(identity.storage_id), InMemoryStore)
    if database_backend == "sqlite":
        engine.dispose()


# SPDX-License-Identifier: AGPL-3.0-only


def test_curriculum_exposes_only_current_authorized_assignments(boundary):
    client, _, _, file, authorization = boundary
    response = client.get("/api/curriculum", headers=headers()).json()
    assert response["modules"][0]["exercises"][0]["exercise_version"] == "v1"
    assert client.get("/api/curriculum", headers=headers("subject-no-grant")).json() == {
        "modules": []
    }
    authorization["exercise_versions"]["echo-1"] = "v2"
    file.write_text(json.dumps(authorization))
    assert client.get("/api/curriculum", headers=headers()).json() == {"modules": []}


def test_registration_anon_code_cannot_forge_learner(boundary):
    response = boundary[0].post(
        "/api/participant", json={"anon_code": "gh:2", "consent": True}, headers=headers()
    )
    assert response.status_code == 404
    assert boundary[1]._consent_cache == {}


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": float("inf")},
        {"nbf": True},
        {"sub": ""},
        {"sub": "student@example.invalid"},
        {"exp": int(time.time()) + 3600},
    ],
)
def test_malformed_dates_and_long_lived_tokens_rejected(boundary, claims):
    assert (
        boundary[0]
        .get("/api/goals/gh:1", headers={"Authorization": "Bearer " + token("subject-a", **claims)})
        .status_code
        == 401
    )


def test_config_tampering_fails_closed(boundary):
    client, _, _, file, authorization = boundary
    authorization["subjects"]["subject-a"][0]["assignments"]["echo-1"] = "student@example.invalid"
    file.write_text(json.dumps(authorization))
    assert client.get("/api/goals/gh:1", headers=headers()).status_code == 503


def test_credentials_and_denials_never_logged(boundary, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        signed = token("subject-a")
        boundary[0].post(
            "/api/run",
            json={**ENDPOINTS[2][2], "participant_id": "gh:2", "source": "unique-private-source"},
            headers={"Authorization": "Bearer " + signed},
        )
    assert signed not in caplog.text and "unique-private-source" not in caplog.text


def test_api_pii_boundary_no_persistence(boundary):
    response = boundary[0].post(
        "/api/goals",
        json={"participant_id": "gh:1", "text": "email me at a@b.edu"},
        headers=headers(),
    )
    assert response.status_code == 422
    assert boundary[1]._ephemeral == {}


def test_standalone_sidecar_is_protected(boundary):
    app = FastAPI()
    app.include_router(build_router(ConsentRouter(InMemoryStore()), SkeletonPack(), lambda: None))
    assert TestClient(app).post("/quad/v1/events", json={"pseudo_id": "gh:1"}).status_code == 401


def test_local_mode_still_requires_signed_credentials(boundary, monkeypatch):
    monkeypatch.setattr(settings, "belay_env", "local")
    assert boundary[0].get("/api/goals/gh:1").status_code == 401
    assert boundary[0].get("/api/goals/gh:1", headers=headers()).status_code == 200


def test_register_repeat_is_stable_and_scoped(boundary):
    client, router, _, _, _ = boundary
    body = {"anon_code": "gh:1", "consent": True}
    first = client.post("/api/participant", json=body, headers=headers()).json()
    second = client.post("/api/participant", json=body, headers=headers()).json()
    assert first == second and first["id"] == "gh:1"
    assert len(router._consent_cache) == 1


def test_openapi_declares_bearer_on_protected_routes(boundary):
    schema = boundary[0].get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    for method, path, _ in ENDPOINTS:
        # Concrete path values are published as path templates.
        path = path.replace("gh:1", "{pid}")
        assert schema["paths"][path][method.lower()]["security"] == [{"HTTPBearer": []}]
    assert "security" not in schema["paths"]["/healthz"]["get"]


def test_route_inventory_has_no_unprotected_learner_route(boundary):
    from fastapi.routing import APIRoute

    from app.auth import authorize

    for route in boundary[0].app.routes:
        if isinstance(route, APIRoute) and (
            route.path.startswith("/api/")
            or route.path.startswith("/quad/v1/")
            and route.path not in {"/quad/v1/health", "/quad/v1/capabilities"}
        ):
            assert any(dep.call is authorize for dep in route.dependant.dependencies), route.path


@pytest.mark.parametrize("field", ["event", "mode", "stance"])
def test_sidecar_trace_metadata_cannot_carry_free_text(boundary, field):
    response = boundary[0].post(
        "/quad/v1/turn",
        json={
            "pseudo_id": "gh:1",
            "exercise_id": "echo-1",
            "stance": "control",
            field: "arbitrary private text",
        },
        headers=headers(),
    )
    assert response.status_code == 422
    assert boundary[1]._consent_cache == {} and boundary[2] == []


def test_quad_omitted_consent_preserves_explicit_research_choice(boundary):
    client, router, _, _, _ = boundary
    client.post("/api/participant", headers=headers(), json={"anon_code": "gh:1", "consent": True})
    for path, body in [
        ("/quad/v1/goals", {"text": "learn"}),
        ("/quad/v1/reflection", {"text": "I understood"}),
        ("/quad/v1/overlay", {"overlay": None}),
        ("/quad/v1/turn", {"exercise_id": "echo-1", "stance": "control"}),
    ]:
        assert client.post(path, headers=headers(), json=body).status_code == 200
        assert router._lookup_consent(Identity("inst-a", "class-a", "gh:1", ()).storage_id) is True
    assert (
        client.post(
            "/quad/v1/goals", headers=headers(), json={"text": "learn", "consent": False}
        ).status_code
        == 200
    )
    assert router._lookup_consent(Identity("inst-a", "class-a", "gh:1", ()).storage_id) is False
