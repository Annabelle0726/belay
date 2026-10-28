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


def test_timeout_retains_uncertainty_and_replay_never_calls_again(ledger):
    ledger.update_policy(policy(version="v2", deployment=Limits(tokens=100000)))
    service, job = queue(ledger)

    class Timeout(Adapter):
        def execute(self, job):
            self.executed += 1

            def call():
                raise TimeoutError("response lost")

            return model_call(call, "test", 10, lambda result: (1, 1))

    adapter = Timeout()
    run_one(service, adapter)
    state = service.status(SCOPE, job["id"])
    assert state["state"] == "unknown" and state["reason"] == "execution_unknown"
    assert ledger.summary()["reserved"]["tokens"] == 1038
    assert service.submit(SCOPE, "op", "a" * 64, "b" * 32, 10, Amount()) == state
    assert not run_one(service, adapter)
    assert adapter.executed == 1


def test_received_result_without_usage_can_complete_but_keeps_hold(ledger):
    ledger.update_policy(policy(version="v2", deployment=Limits(tokens=100000)))
    service, job = queue(ledger)

    class MissingUsage(Adapter):
        def execute(self, job):
            return model_call(lambda: "c" * 32, "test", 10, lambda result: (None, None))

    run_one(service, MissingUsage())
    assert service.status(SCOPE, job["id"])["state"] == "completed"
    assert ledger.summary()["reserved"]["tokens"] == 1038


def test_invalid_adapter_result_never_completes(ledger):
    service, job = queue(ledger)

    class Empty(Adapter):
        def execute(self, job):
            return ""

    run_one(service, Empty())
    state = service.status(SCOPE, job["id"])
    assert state["state"] == "failed" and state["reason"] == "invalid_result_ref"


def test_late_result_cannot_publish_or_start_next_call(ledger):
    ledger.update_policy(
        policy(version="v2", execution_seconds=10, deployment=Limits(tokens=100000))
    )
    service, job = queue(ledger)
    calls = []

    class Late(Adapter):
        def execute(self, job):
            def call():
                calls.append(1)
                ledger.clock = lambda: 111.0
                return "c" * 32

            model_call(call, "test", 10, lambda result: (1, 1))
            return model_call(call, "test", 10, lambda result: (1, 1))

    run_one(service, Late())
    state = service.status(SCOPE, job["id"])
    assert state["state"] == "unknown" and state["reason"] == "execution_deadline"
    assert state["result_ref"] is None and calls == [1]
    # A known completed attempt is still settled, even if publication was fenced.
    assert ledger.summary()["consumed"]["tokens"] == 2


def test_coordinator_outage_never_falls_back(ledger):
    from app.controls.ledger import metadata

    metadata.drop_all(ledger.engine)
    with pytest.raises(ControlError, match="coordinator_unavailable"):
        ledger.reserve("a", "op", SCOPE, Amount(tokens=1), "model")


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/run",
            {"participant_id": "gh:12345", "exercise_id": "ds-foundations", "source": "pass"},
        ),
        ("/api/sol/turn", {"participant_id": "gh:12345", "exercise_id": "ds-foundations"}),
        ("/quad/v1/turn", {"pseudo_id": "gh:12345", "exercise_id": "ds-foundations"}),
    ],
)
def test_http_enforcement_cannot_trust_body_identity(monkeypatch, path, payload):
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app
    from tests.http_auth import authenticated_client

    monkeypatch.setattr(settings, "controls_mode", "enforced")
    monkeypatch.setattr(settings, "controls_jobs_enabled", False)
    with TestClient(app) as anonymous:
        assert anonymous.post(path, json=payload).status_code == 401
        assert anonymous.get("/api/curriculum").status_code == 401
    with authenticated_client(app) as client:
        forged = {**payload, "learner_id": "gh:999"}
        assert client.post(path, json=forged).status_code == 404
        result = client.post(path, json=payload)
        assert result.status_code == 503
        # Run now creates its trusted context from authenticated authority, but
        # still cannot execute with the controlled service disabled. Legacy
        # synchronous model routes continue to require a worker context.
        expected = "jobs_disabled" if path == "/api/run" else "verified_execution_required"
        assert result.json()["detail"]["code"] == expected
        assert client.get("/api/curriculum").status_code == 200


@pytest.mark.parametrize("status", [401, 403, 500])
def test_provider_auth_rejection_finishes_but_uncertain_failure_stays_blocked(
    ledger, caplog, status
):
    from sqlalchemy import select

    from app.controls.admission import slots

    ledger.update_policy(policy(version="v2", deployment=Limits(tokens=100000)))
    service, job = queue(ledger)

    # The shared runtime consumes status_code across providers; constructing an
    # SDK HTTP response would unnecessarily couple this worker test to httpx.
    class ProviderStatusError(Exception):
        def __init__(self):
            super().__init__("PRIVATE_SECRET_AND_PROMPT https://example.invalid/chat/completions")
            self.status_code = status

    class Rejected(Adapter):
        def execute(self, job):
            self.executed += 1

            def call():
                raise ProviderStatusError()

            return model_call(call, "private prompt", 10, lambda result: (1, 1))

    adapter = Rejected()
    assert run_one(service, adapter)
    result = service.status(SCOPE, job["id"])
    assert result["state"] == ("failed" if status in {401, 403} else "unknown")
    assert result["reason"] == (
        "provider_auth_failed" if status in {401, 403} else "execution_unknown"
    )
    assert ledger.summary()["reserved"]["tokens"] > 0  # No invented zero-usage refund.
    with ledger.transaction() as conn:
        slot = conn.execute(select(slots)).mappings().one()
    assert slot["state"] == ("released" if status in {401, 403} else "unknown")
    assert not run_one(service, adapter)
    assert adapter.executed == 1
    assert "PRIVATE_SECRET_AND_PROMPT" not in caplog.text
    assert "private prompt" not in caplog.text
    assert "example.invalid" not in caplog.text
    assert "model_call_failed" in caplog.text
