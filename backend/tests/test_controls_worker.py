# SPDX-License-Identifier: AGPL-3.0-only
import pytest

from app.controls.admission import Admission
from app.controls.contracts import Amount, ControlError, Limits
from app.controls.runtime import model_call
from app.controls.worker import run_one
from conftest import CONTROL_SCOPE as SCOPE
from conftest import controls_policy as policy


class Adapter:
    def __init__(self):
        self.allowed = True
        self.executed = 0

    def check(self, job):
        if not self.allowed:
            raise ControlError("authorization_revoked", 403)
        return SCOPE

    def execute(self, job):
        self.executed += 1
        return "c" * 32


def queue(ledger):
    service = Admission(ledger)
    job = service.submit(SCOPE, "op", "a" * 64, "b" * 32, 10, Amount())
    return service, job


def test_deleted_before_dispatch_never_executes(ledger):
    service, job = queue(ledger)
    adapter = Adapter()
    adapter.allowed = False
    assert run_one(service, adapter)
    assert adapter.executed == 0
    assert service.status(SCOPE, job["id"])["result_ref"] is None


def test_revoked_during_execution_never_publishes(ledger):
    service, job = queue(ledger)

    class Revoke(Adapter):
        def execute(self, job):
            self.allowed = False
            return "c" * 32

    assert run_one(service, Revoke())
    assert service.status(SCOPE, job["id"])["state"] == "failed"


def test_cancellation_prevents_next_attempt(ledger):
    ledger.update_policy(policy(version="v2", deployment=Limits(tokens=100000)))
    service, job = queue(ledger)
    calls = []

    class Cancel(Adapter):
        def execute(self, claimed):
            service.cancel(SCOPE, job["id"])
            return model_call(lambda: calls.append(1), "test", 10, lambda result: (1, 1))

    run_one(service, Cancel())
    assert calls == []
    assert service.status(SCOPE, job["id"])["state"] == "cancelled"


def test_stale_worker_cannot_start_next_external_attempt(ledger):
    service, job = queue(ledger)
    calls = []

    class Expire(Adapter):
        def execute(self, claimed):
            ledger.clock = lambda: 500.0
            return model_call(lambda: calls.append(1), "test", 10, lambda result: (1, 1))

    run_one(service, Expire())
    assert calls == []
    assert service.status(SCOPE, job["id"])["state"] == "unknown"


def test_success_and_completed_replay(ledger):
    service, job = queue(ledger)
    adapter = Adapter()
    run_one(service, adapter)
    replay = service.submit(SCOPE, "op", "a" * 64, "b" * 32, 10, Amount())
    assert replay["state"] == "completed" and replay["result_ref"] == "c" * 32
    assert not run_one(service, adapter)
    assert adapter.executed == 1


def test_coordinator_outage_never_falls_back(ledger):
    from app.controls.ledger import metadata

    metadata.drop_all(ledger.engine)
    with pytest.raises(ControlError, match="coordinator_unavailable"):
        ledger.reserve("a", "op", SCOPE, Amount(tokens=1), "model")


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/run", {"participant_id": "p", "exercise_id": "ds-foundations", "source": "pass"}),
        ("/api/sol/turn", {"participant_id": "p", "exercise_id": "ds-foundations"}),
        ("/quad/v1/turn", {"pseudo_id": "gh:12345", "exercise_id": "ds-foundations"}),
    ],
)
def test_http_enforcement_cannot_trust_body_identity(monkeypatch, path, payload):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "controls_mode", "enforced")
    with TestClient(app) as client:
        result = client.post(path, json=payload)
        assert result.status_code == 503
        assert result.json()["detail"]["code"] == "verified_execution_required"
        assert client.get("/api/curriculum").status_code == 200
