# SPDX-License-Identifier: AGPL-3.0-only
import multiprocessing as mp
import os
import uuid
from concurrent.futures import ProcessPoolExecutor

import pytest
from sqlalchemy import create_engine

from app.controls.contracts import Amount, ControlError, Limits, Policy, Scope
from app.controls.ledger import Ledger, metadata


def policy(**kwargs):
    values = dict(
        version="test-v1",
        price_version="synthetic-v1",
        currency="USD",
        input_price=1,
        output_price=2,
        deployment=Limits(tokens=1000),
        institution=Limits(),
        classroom=Limits(),
        learner=Limits(),
    )
    values.update(kwargs)
    return Policy(**values)


@pytest.fixture
def ledger(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'controls.db'}")
    value = Ledger(engine, lambda: 100.0)
    value.initialize(policy())
    yield value
    engine.dispose()


SCOPE = Scope("test", "i", "c", "l")


def test_atomic_parent_child_and_idempotency(ledger):
    ledger.reserve("a", "op", SCOPE, Amount(tokens=800), "model")
    ledger.reserve("a", "op", SCOPE, Amount(tokens=800), "model")
    with pytest.raises(ControlError, match="budget_exhausted"):
        ledger.reserve("b", "op2", Scope("test", "i2", "c2", "l2"), Amount(tokens=800), "model")
    with pytest.raises(ControlError, match="attempt_conflict"):
        ledger.reserve("a", "op", SCOPE, Amount(tokens=1), "model")
    ledger.settle("a", Amount(tokens=100))
    ledger.settle("a", Amount(tokens=100))
    with pytest.raises(ControlError, match="settlement_conflict"):
        ledger.settle("a", Amount(tokens=101))
    ledger.reserve("b", "op2", SCOPE, Amount(tokens=800), "model")
    assert ledger.summary()["consumed"]["tokens"] == 100


@pytest.mark.parametrize("level", ["institution", "classroom", "learner"])
def test_child_limits(ledger, level):
    ledger.update_policy(policy(version="v2", **{level: Limits(tokens=10)}))
    with pytest.raises(ControlError, match="budget_exhausted"):
        ledger.reserve("a", "op", SCOPE, Amount(tokens=11), "model")
    assert ledger.summary()["attempts"] == 0


def test_unknown_carries_across_rollover_and_reconciles(ledger):
    ledger.reserve("a", "op", SCOPE, Amount(tokens=800), "model")
    ledger.settle("a", None)
    ledger.clock = lambda: 90000.0
    with pytest.raises(ControlError, match="budget_exhausted"):
        ledger.reserve("b", "op", SCOPE, Amount(tokens=800), "model")
    ledger.settle("a", Amount(tokens=300))
    ledger.reserve("b", "op", SCOPE, Amount(tokens=800), "model")


def test_overrun_records_actual_and_stops_next_attempt(ledger):
    ledger.reserve("a", "op", SCOPE, Amount(tokens=1), "model")
    ledger.settle("a", Amount(tokens=2))
    assert ledger.summary()["consumed"]["tokens"] == 2
    with pytest.raises(ControlError, match="unresolved_overrun"):
        ledger.reserve("b", "op", SCOPE, Amount(tokens=1), "model")


def test_policy_validation_and_snapshot(ledger):
    with pytest.raises(ValueError):
        policy(input_price=-1)
    with pytest.raises(ValueError):
        Amount(tokens=True)
    ledger.reserve("a", "op", SCOPE, Amount(tokens=10), "model")
    ledger.update_policy(policy(version="v2", input_price=4))
    row = ledger.reserve("a", "op", SCOPE, Amount(tokens=10), "model")
    assert row["policy"]["input_price"] == 1
    with pytest.raises(ValueError, match="migration"):
        ledger.update_policy(policy(version="v3", period_seconds=60))


def _race_reserve(url, scope_id, attempt_id):
    engine = create_engine(url)
    ledger = Ledger(engine)
    try:
        ledger.reserve(
            attempt_id,
            attempt_id,
            Scope(scope_id, "i", "c", attempt_id),
            Amount(tokens=800),
            "model",
        )
        return "accepted"
    except ControlError as exc:
        return exc.code
    finally:
        engine.dispose()


def test_postgres_two_process_reservation():
    url = os.environ.get("CONTROL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL database")
    engine = create_engine(url)
    assert engine.dialect.name == "postgresql"
    # This variable is deliberately separate from application DATABASE_URL.
    metadata.drop_all(engine)
    ledger = Ledger(engine)
    ledger.initialize(policy())
    scope_id = uuid.uuid4().hex
    with ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as pool:
        results = list(pool.map(_race_reserve, [url] * 2, [scope_id] * 2, ["race-a", "race-b"]))
    assert sorted(results) == ["accepted", "budget_exhausted"]
    engine.dispose()
