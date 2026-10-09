# SPDX-License-Identifier: AGPL-3.0-only
import multiprocessing as mp
import os
import uuid
from concurrent.futures import ProcessPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy import inspect as inspect_db

from app.controls.admission import Admission
from app.controls.contracts import Amount, ControlError, Limits, Scope, Traffic
from app.controls.ledger import Ledger, metadata
from conftest import CONTROL_SCOPE as SCOPE
from conftest import controls_policy as policy


def submit(service, scope=SCOPE, op=None, **kwargs):
    return service.submit(
        scope,
        op or uuid.uuid4().hex,
        "a" * 64,
        "b" * 32,
        kwargs.get("size", 10),
        Amount(tokens=kwargs.get("tokens", 0)),
    )


def test_rotation_and_class_fifo(ledger):
    service = Admission(ledger)
    for i in range(50):
        submit(service, op=f"a{i}")
    other = Scope("test", "i", "B", "l")
    for i in range(2):
        submit(service, other, op=f"b{i}")
    claimed = [service.claim() for _ in range(4)]
    assert [j["operation"] for j in claimed] == ["a0", "b0", "a1", "b1"]


def test_queue_bounds_rate_and_bytes(ledger):
    service = Admission(ledger)
    ledger.update_policy(policy(version="v2", deployment_traffic=Traffic(queue_jobs=1)))
    submit(service)
    with pytest.raises(ControlError, match="queue_full"):
        submit(service)
    ledger.update_policy(policy(version="v3", deployment_traffic=Traffic(queue_bytes=15)))
    with pytest.raises(ControlError, match="queue_full"):
        submit(service)
    with pytest.raises(ControlError, match="payload_too_large"):
        submit(service, size=1000000)


def test_token_bucket_is_shared_and_refills(ledger):
    ledger.update_policy(policy(version="v2", deployment_traffic=Traffic(burst=1, rate_seconds=10)))
    submit(Admission(ledger))
    with pytest.raises(ControlError, match="rate_limited"):
        submit(Admission(ledger))
    ledger.clock = lambda: 110.0
    submit(Admission(ledger))


def test_idempotency_cancellation_and_scoped_polling(ledger):
    service = Admission(ledger)
    job = submit(service, op="same", tokens=800)
    assert submit(service, op="same", tokens=800) == job
    with pytest.raises(ControlError, match="operation_conflict"):
        service.submit(SCOPE, "same", "c" * 64, "b" * 32, 10, Amount(tokens=800))
    with pytest.raises(ControlError, match="job_unavailable"):
        service.status(Scope("test", "i", "c", "other"), job["id"])
    assert service.status(SCOPE, job["id"])["state"] == "queued"
    with pytest.raises(ControlError, match="poll_limited"):
        service.status(SCOPE, job["id"])
    service.cancel(SCOPE, job["id"])
    service.cancel(SCOPE, job["id"])
    assert ledger.summary()["reserved"]["tokens"] == 0
    assert service.claim() is None


def test_queue_liability_funding_recheck_and_expiry(ledger):
    service = Admission(ledger)
    submit(service, tokens=800)
    with pytest.raises(ControlError, match="budget_exhausted"):
        submit(service, tokens=800)
    ledger.update_policy(policy(version="v2", deployment=Limits(tokens=500)))
    assert service.claim() is None
    ledger.clock = lambda: 500.0
    assert service.claim() is None
    assert ledger.summary()["reserved"]["tokens"] == 0


def test_concurrency_and_unknown_are_not_released_on_expiry(ledger):
    ledger.update_policy(
        policy(
            version="v2", deployment_traffic=Traffic(active_jobs=1, model_calls=1, runner_calls=1)
        )
    )
    service = Admission(ledger)
    submit(service)
    submit(service)
    job = service.claim()
    assert service.claim() is None
    slot = service.acquire_slot(SCOPE, job["id"], "model")
    with pytest.raises(ControlError, match="concurrency_limited"):
        service.acquire_slot(SCOPE, job["id"], "model")
    runner = service.acquire_slot(SCOPE, job["id"], "runner")
    service.release_slot(runner, stopped=True)
    service.release_slot(slot, stopped=False)
    ledger.clock = lambda: 170.0
    assert service.claim() is None
    with pytest.raises(ControlError, match="stale_worker"):
        service.finish(job["id"], job["fence"], authorized=True)
    with pytest.raises(ControlError, match="concurrency_limited"):
        service.acquire_slot(SCOPE, job["id"], "model")


def test_running_cancel_and_revocation_never_publish(ledger):
    service = Admission(ledger)
    job = submit(service)
    claim = service.claim()
    service.cancel(SCOPE, job["id"])
    with pytest.raises(ControlError, match="cancel_requested"):
        service.heartbeat(job["id"], claim["fence"])
    service.finish(job["id"], claim["fence"], "c" * 32, authorized=True)
    result = service.status(SCOPE, job["id"])
    assert result["state"] == "cancelled" and result["result_ref"] is None
    job2 = submit(service)
    claim2 = service.claim()
    service.finish(job2["id"], claim2["fence"], "c" * 32, authorized=False)
    assert service.status(SCOPE, job2["id"])["result_ref"] is None


@pytest.mark.parametrize("result", [None, ""])
def test_completion_requires_result_reference(ledger, result):
    service = Admission(ledger)
    job = submit(service)
    claim = service.claim()
    with pytest.raises(ControlError, match="invalid_result_ref"):
        service.finish(job["id"], claim["fence"], result, authorized=True)
    assert service.status(SCOPE, job["id"])["state"] == "running"


def test_heartbeats_and_policy_changes_cannot_extend_execution(ledger):
    ledger.update_policy(policy(version="v2", execution_seconds=120))
    service = Admission(ledger)
    job = submit(service)
    claim = service.claim()
    for now in (150.0, 200.0):
        ledger.clock = lambda now=now: now
        service.heartbeat(job["id"], claim["fence"])
    ledger.update_policy(policy(version="v3", execution_seconds=3600))
    ledger.clock = lambda: 220.0
    with pytest.raises(ControlError, match="stale_worker"):
        service.heartbeat(job["id"], claim["fence"])
    state = service.status(SCOPE, job["id"])
    assert state["state"] == "unknown" and state["reason"] == "execution_deadline"


def test_explicit_schema_upgrade_fences_legacy_active_jobs(ledger):
    service = Admission(ledger)
    job = submit(service)
    service.claim()
    with ledger.engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE control_jobs DROP COLUMN deadline")
    ledger.upgrade_schema()
    ledger.upgrade_schema()  # Operator replay is safe.
    assert "deadline" in {c["name"] for c in inspect_db(ledger.engine).get_columns("control_jobs")}
    state = service.status(SCOPE, job["id"])
    assert state["state"] == "unknown"
    assert service.claim() is None


def test_cancellation_does_not_claim_uncertain_external_work_stopped(ledger):
    service = Admission(ledger)
    job = submit(service)
    claim = service.claim()
    slot = service.acquire_slot(SCOPE, job["id"], "model")
    service.release_slot(slot, stopped=False)
    service.cancel(SCOPE, job["id"])
    service.finish(job["id"], claim["fence"], authorized=False)
    assert service.status(SCOPE, job["id"])["state"] == "unknown"


def _slot_race(url, number):
    engine = create_engine(url)
    try:
        service = Admission(Ledger(engine))
        service.acquire_slot(SCOPE, str(number), "model")
        return "accepted"
    except ControlError as exc:
        return exc.code
    finally:
        engine.dispose()


def test_postgres_legacy_schema_upgrade_preserves_liability():
    url = os.environ.get("CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL database")
    engine = create_engine(url)
    try:
        metadata.drop_all(engine)
        ledger = Ledger(engine, lambda: 100.0)
        ledger.initialize(policy())
        service = Admission(ledger)
        job = submit(service)
        service.claim()
        ledger.reserve("legacy-attempt", job["id"], SCOPE, Amount(tokens=800), "model")
        service.acquire_slot(SCOPE, job["id"], "model")
        with ledger.transaction() as conn:
            conn.exec_driver_sql("ALTER TABLE control_jobs DROP COLUMN deadline")
        ledger.upgrade_schema()
        ledger.upgrade_schema()
        assert service.status(SCOPE, job["id"])["state"] == "unknown"
        assert ledger.summary()["reserved"]["tokens"] == 800
        assert service.claim() is None
    finally:
        engine.dispose()


def test_postgres_two_process_concurrency_cap():
    url = os.environ.get("CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL database")
    engine = create_engine(url)
    metadata.drop_all(engine)
    Ledger(engine).initialize(policy())
    with ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as pool:
        results = list(pool.map(_slot_race, [url] * 20, range(20)))
    assert results.count("accepted") == 10
    assert results.count("concurrency_limited") == 10
    engine.dispose()
