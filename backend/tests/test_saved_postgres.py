# SPDX-License-Identifier: AGPL-3.0-only
"""Independent API/worker processes and real PostgreSQL transaction races."""

import json
import multiprocessing as mp
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from app.auth import recheck_grant
from app.config import settings
from app.controls import jobs_http
from app.controls.admission import jobs
from app.controls.contracts import ControlError, Limits
from app.controls.data import ExecutionData, data
from app.controls.jobs_worker import AskAdapter
from app.controls.ledger import Ledger, attempts
from app.controls.worker import run_one
from app.conversations.ledger import DeletionLedger
from app.conversations.migration import migrate
from app.conversations.models import Message
from app.conversations.policy import Policy
from app.conversations.repository import ConversationStore
from app.conversations.router import build_router
from app.packs._skeleton.pack import SkeletonPack
from app.store import ConsentRouter, InMemoryStore
from conftest import _CallStub, controls_policy
from tests.http_auth import token
from tests.test_controls_execution import provider, response
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_saved_jobs import body


def _open(args):
    url, key, config, cid, _ = args
    for name, value in config.items():
        setattr(settings, name, value)
    os.environ["TUTOR_PACK"] = "_skeleton"
    engine = create_engine(url)
    store = ExecutionData(Ledger(engine, lambda: 100.0), "test", key)
    store.dialogue = ConversationStore(engine, Policy.from_settings(settings), lambda: 100)
    jobs_http.execution_store = lambda: store
    return store, cid


def _api(args, action="submit", started=None):
    store, cid = _open(args)
    app = FastAPI()
    app.include_router(
        build_router(
            "/api",
            ConsentRouter(InMemoryStore()),
            SkeletonPack(),
            lambda: None,
            engine=store.ledger.engine,
            repository_factory=lambda: store.dialogue,
        )
    )
    try:
        if started:
            started.set()
        with TestClient(app, headers={"Authorization": "Bearer " + args[4]}) as client:
            path = f"/api/conversations/{cid}"
            result = (
                client.post(path + "/jobs", json=body())
                if action == "submit"
                else client.delete(path)
            )
            return result.status_code, None if result.status_code == 204 else result.json()
    finally:
        store.ledger.engine.dispose()


def _worker(args, mode="normal", ready=None, release=None):
    store, _ = _open(args)
    stub = _CallStub()
    llm, calls = provider(
        [
            response(json.dumps(stub.json(role=role, tier="fast", system="", user="")))
            for role in ("planner", "reasoner", "self_eval")
        ]
    )
    adapter = AskAdapter(store, ConsentRouter(InMemoryStore()), SkeletonPack(), lambda: llm)
    if mode == "before_publish":
        original = adapter.publish

        def held(*args):
            ready.set()
            if not release.wait(20):
                raise TimeoutError()
            original(*args)

        adapter.publish = held
    elif mode in {"during_publish", "crash_publish"}:
        original = store.dialogue.complete

        def complete_held(*args, **kwargs):
            result = original(*args, **kwargs)
            if mode == "crash_publish":
                os._exit(17)  # SQL server must roll back the uncommitted connection.
            ready.set()
            if not release.wait(20):
                raise TimeoutError()
            return result

        store.dialogue.complete = complete_held
    try:
        return run_one(store.admission, adapter), len(calls)
    finally:
        store.ledger.engine.dispose()


@pytest.fixture
def shared(grant_boundary, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TUTOR_PACK", "_skeleton")
    base = os.environ.get("CONTROL_TEST_DATABASE_URL")
    if not base:
        pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL")
    schema = "saved_ask_" + uuid.uuid4().hex
    admin = create_engine(base)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    url = (
        make_url(base)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    engine = create_engine(url)
    ledger = Ledger(engine, lambda: 100.0)
    ledger.initialize(controls_policy(deployment=Limits(tokens=1000000)))
    migrate(engine)
    policy = Policy(
        enabled=True,
        policy_id="pg-saved",
        retention_seconds=600,
        backup_max_age_seconds=600,
        deletion_ledger_file=str(tmp_path / "deleted.jsonl"),
    )
    for field in fields(policy):
        monkeypatch.setattr(settings, "dialogue_" + field.name, getattr(policy, field.name))
    monkeypatch.setattr(settings, "controls_mode", "enforced")
    DeletionLedger(policy.deletion_ledger_file).initialize()
    repo = ConversationStore(engine, policy, lambda: 100)
    identity = recheck_grant(grant_boundary[0])
    cid = repo.create(identity, "create")["conversation_id"]
    names = [
        "belay_env",
        "auth_issuer",
        "auth_audience",
        "auth_public_key_file",
        "auth_authorization_file",
        "controls_mode",
    ]
    names += ["dialogue_" + field.name for field in fields(policy)]
    args = (
        url,
        Fernet.generate_key(),
        {name: getattr(settings, name) for name in names},
        cid,
        token("original"),
    )
    yield args, ledger, repo, identity
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin.dispose()


def test_postgres_saved_duplicate_across_two_api_and_worker_processes(shared):
    args, ledger, repo, identity = shared
    with ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as pool:
        results = list(pool.map(_api, [args, args]))
        assert [r[0] for r in results] == [202, 202]
        assert results[0][1]["id"] == results[1][1]["id"]
        assert sorted(pool.map(_worker, [args, args])) == [(False, 0), (True, 3)]
    assert len(repo.history(identity, args[3])["messages"]) == 2
    with ledger.transaction() as conn:
        assert conn.execute(select(jobs.c.state)).scalar_one() == "completed"
        assert len(conn.execute(select(attempts).where(attempts.c.kind == "model")).all()) == 3
    assert ledger.summary()["consumed"]["tokens"] == 45


@pytest.mark.parametrize("mode", ["before_publish", "during_publish"])
def test_postgres_delete_and_publish_compete_without_resurrection_or_result_leak(shared, mode):
    args, ledger, repo, _ = shared
    assert _api(args)[0] == 202
    context = mp.get_context("spawn")
    with context.Manager() as manager:
        ready, release, deleting = manager.Event(), manager.Event(), manager.Event()
        with ProcessPoolExecutor(2, mp_context=context) as pool:
            worker = pool.submit(_worker, args, mode, ready, release)
            assert ready.wait(20)
            removal = pool.submit(_api, args, "delete", deleting)
            assert deleting.wait(20)
            if mode == "before_publish":
                assert removal.result(timeout=20)[0] == 204
            else:
                deadline = time.monotonic() + 10
                while True:
                    with ledger.engine.connect() as conn:
                        waiting = conn.execute(
                            text(
                                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE 'UPDATE conversations%' AND pid <> pg_backend_pid()"
                            )
                        ).scalar_one()
                    if waiting:
                        break
                    assert (
                        time.monotonic() < deadline
                    ), "delete did not contend on the publication row lock"
                    time.sleep(0.05)
                assert not removal.done()
            release.set()
            assert worker.result(timeout=20)[1] == 3
            assert removal.result(timeout=20)[0] == 204
    with ledger.transaction() as conn:
        assert conn.execute(select(data)).all() == []
    with repo.sessions() as session:
        assert session.scalars(select(Message)).all() == []
    store, _ = _open(args)
    try:
        with pytest.raises(ControlError) as error:
            store.status(shared[3], store.job_id(shared[3], "saved_request_001"))
        assert getattr(error.value, "status", None) == 404
    finally:
        store.ledger.engine.dispose()


def test_postgres_process_exit_during_publish_rolls_back_both_systems(shared):
    args, ledger, repo, _ = shared
    assert _api(args)[0] == 202
    context = mp.get_context("spawn")
    process = context.Process(target=_worker, args=(args, "crash_publish"))
    process.start()
    process.join(25)
    if process.is_alive():
        process.terminate()
        process.join(5)
        pytest.fail("worker did not reach injected crash")
    assert process.exitcode == 17
    with repo.sessions() as session:
        assert len(session.scalars(select(Message)).all()) == 1
    ledger.clock = lambda: 161.0
    with ledger.transaction() as conn:
        from app.controls.admission import Admission

        Admission(ledger)._expire(conn, ledger.now(conn))
        assert conn.execute(select(jobs.c.state)).scalar_one() == "unknown"
    assert _worker(args) == (False, 0)
    assert ledger.summary()["consumed"]["tokens"] == 45
