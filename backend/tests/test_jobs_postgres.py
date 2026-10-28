# SPDX-License-Identifier: AGPL-3.0-only
"""Two independent signed HTTP processes + real worker adapters, no provider network."""

import json
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.config import settings
from app.controls import jobs_http
from app.controls.admission import jobs
from app.controls.contracts import Limits, Traffic
from app.controls.data import ExecutionData, data
from app.controls.jobs_worker import AskAdapter
from app.controls.ledger import Ledger, attempts, metadata
from app.controls.worker import run_one
from app.packs._skeleton.pack import SkeletonPack
from app.store import ConsentRouter, InMemoryStore
from conftest import _CallStub, controls_policy
from tests.http_auth import token
from tests.test_controls_execution import provider, response
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_jobs_http import BODY


def _store(arguments):
    url, key, config, _ = arguments
    for name, value in config.items():
        setattr(settings, name, value)
    os.environ["TUTOR_PACK"] = "_skeleton"
    engine = create_engine(url)
    return ExecutionData(Ledger(engine), "test", key)


def _submit_process(arguments):
    store = _store(arguments)
    jobs_http.execution_store = lambda: store
    app = FastAPI()
    app.include_router(jobs_http.build_jobs_router("/api/sol/jobs", SkeletonPack()))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/sol/jobs",
                json={**BODY, "stance": "peer"},
                headers={"Authorization": "Bearer " + arguments[3]},
            )
            return response.status_code, response.json()
    finally:
        store.ledger.engine.dispose()


def _worker_process(arguments):
    store = _store(arguments)
    stub = _CallStub()
    llm, calls = provider(
        [
            response(json.dumps(stub.json(role=role, tier="fast", system="", user="")))
            for role in ("planner", "reasoner", "self_eval")
        ]
    )
    try:
        adapter = AskAdapter(store, ConsentRouter(InMemoryStore()), SkeletonPack(), lambda: llm)
        return run_one(store.admission, adapter), len(calls)
    finally:
        store.ledger.engine.dispose()


def test_postgres_signed_duplicate_across_api_and_worker_processes(grant_boundary):  # noqa: F811
    url = os.environ.get("CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL database")
    engine = create_engine(url)
    try:
        metadata.drop_all(engine)
        ledger = Ledger(engine)
        ledger.initialize(
            controls_policy(
                deployment=Limits(tokens=1000000), deployment_traffic=Traffic(active_jobs=1)
            )
        )
        config = {
            name: getattr(settings, name)
            for name in (
                "belay_env",
                "auth_issuer",
                "auth_audience",
                "auth_public_key_file",
                "auth_authorization_file",
            )
        }
        args = (url, Fernet.generate_key(), config, token("original"))
        with ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as pool:
            submissions = list(pool.map(_submit_process, [args, args]))
            assert [code for code, _ in submissions] == [202, 202]
            assert submissions[0][1]["id"] == submissions[1][1]["id"]
            results = list(pool.map(_worker_process, [args, args]))
        assert sorted(results) == [(False, 0), (True, 3)]
        with ledger.transaction() as conn:
            rows = list(conn.execute(select(jobs)).mappings())
            assert len(rows) == 1 and rows[0]["state"] == "completed"
            assert [r.kind for r in conn.execute(select(data))] == ["result"]
            assert len(list(conn.execute(select(attempts).where(attempts.c.kind == "model")))) == 3
        assert ledger.summary()["consumed"]["tokens"] == 45
    finally:
        engine.dispose()


def _batch_api_process(arguments):
    base, count, barrier = arguments
    store = _store(base)
    jobs_http.execution_store = lambda: store
    app = FastAPI()
    app.include_router(jobs_http.build_jobs_router("/api/sol/jobs", SkeletonPack()))
    try:
        barrier.wait(timeout=20)
        with TestClient(app) as client:
            results = []
            for n in range(count):
                body = {
                    **BODY,
                    "participant_id": "gh:1" if count == 3 else "gh:2",
                    "stance": "peer",
                    "request_id": f"fairness_request_{n:04}",
                }
                reply = client.post(
                    "/api/sol/jobs", json=body, headers={"Authorization": "Bearer " + base[3]}
                )
                if reply.status_code != 202:
                    raise AssertionError(reply.status_code)
                results.append(reply.json()["id"])
            return os.getpid(), results
    finally:
        store.ledger.engine.dispose()


def _held_worker_process(arguments):
    base, started, release = arguments
    store = _store(base)
    stub = _CallStub()
    llm, calls = provider(
        [
            response(json.dumps(stub.json(role=role, tier="fast", system="", user="")))
            for role in ("planner", "reasoner", "self_eval")
        ]
    )
    create = llm._client.chat.completions.create

    def held(**kwargs):
        if not calls:
            started.set()
            if not release.wait(timeout=20):
                raise TimeoutError("test release missing")
        return create(**kwargs)

    llm._client.chat.completions.create = held
    try:
        adapter = AskAdapter(store, ConsentRouter(InMemoryStore()), SkeletonPack(), lambda: llm)
        return run_one(store.admission, adapter), len(calls)
    finally:
        store.ledger.engine.dispose()


def test_postgres_signed_classes_share_job_cap_and_rotate_fairly(grant_boundary):  # noqa: F811
    url = os.environ.get("CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL database")
    _, path, auth = grant_boundary
    auth["subjects"]["class-b"] = [
        {
            "institution_id": "i",
            "class_id": "class-b",
            "learner_id": "gh:2",
            "assignments": {"echo-1": "v1"},
        }
    ]
    path.write_text(json.dumps(auth))
    engine = create_engine(url)
    try:
        metadata.drop_all(engine)
        ledger = Ledger(engine)
        ledger.initialize(
            controls_policy(
                deployment=Limits(tokens=1000000), deployment_traffic=Traffic(active_jobs=1)
            )
        )
        config = {
            name: getattr(settings, name)
            for name in (
                "belay_env",
                "auth_issuer",
                "auth_audience",
                "auth_public_key_file",
                "auth_authorization_file",
            )
        }
        key = Fernet.generate_key()
        base_a = (url, key, config, token("original"))
        base_b = (url, key, config, token("class-b"))
        with (
            mp.get_context("spawn").Manager() as manager,
            ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as pool,
        ):
            barrier = manager.Barrier(2)
            batches = list(
                pool.map(_batch_api_process, [(base_a, 3, barrier), (base_b, 2, barrier)])
            )
            assert len({pid for pid, _ in batches}) == 2
            with ledger.transaction() as conn:
                scopes = {
                    row["id"]: row["scopes"][2] for row in conn.execute(select(jobs)).mappings()
                }
            started, release = manager.Event(), manager.Event()
            held = pool.submit(_held_worker_process, (base_a, started, release))
            try:
                assert started.wait(timeout=20)
                competing = pool.submit(_worker_process, base_a).result(timeout=20)
                assert competing == (False, 0)
                with ledger.transaction() as conn:
                    assert (
                        len(list(conn.execute(select(jobs).where(jobs.c.state == "running")))) == 1
                    )
                    assert (
                        len(list(conn.execute(select(jobs).where(jobs.c.state == "queued")))) == 4
                    )
            finally:
                release.set()
            assert held.result(timeout=20) == (True, 3)
            order = []
            for n in range(5):
                with ledger.transaction() as conn:
                    completed = {
                        row.id
                        for row in conn.execute(
                            select(jobs.c.id).where(jobs.c.state == "completed")
                        )
                    }
                newly = completed - set(order)
                assert len(newly) == 1
                order.append(newly.pop())
                if n < 4:
                    assert pool.submit(_worker_process, base_a).result(timeout=20) == (True, 3)
            assert all(scopes[order[i]] != scopes[order[i + 1]] for i in range(3))
            for _, expected in batches:
                assert [job for job in order if job in expected] == expected
            assert pool.submit(_worker_process, base_a).result(timeout=20) == (False, 0)
        assert ledger.summary()["consumed"]["tokens"] == 225
    finally:
        engine.dispose()
