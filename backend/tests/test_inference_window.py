# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest

from app import controlled_runtime
from app.config import settings
from app.controls.contracts import Amount, ControlError
from app.controls.runtime import model_call, operation
from conftest import CONTROL_SCOPE
from tests.test_controls_execution import funded


def test_first_start_persists_deadline_and_restarts_cannot_renew_or_disable(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "controls_inference_window_seconds", 3600)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 0)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 62779)
    now = [100.0]
    monkeypatch.setattr(controlled_runtime.time, "time", lambda: now[0])
    manifest = {"schema": 1, "nonce": "same-installation"}
    first = controlled_runtime.arm_inference_window(tmp_path, manifest)
    assert first["inference_window"] == {
        "started": 100.0,
        "expires": 3700.0,
        "total_microunits": 62779,
    }
    stored = (tmp_path / "runtime.json").read_bytes()
    now[0] = 200.0
    monkeypatch.setattr(settings, "controls_inference_window_seconds", 0)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", None)
    restarted = controlled_runtime.arm_inference_window(tmp_path, json.loads(stored))
    assert restarted == first and settings.controls_inference_expires_at == 3700.0
    assert settings.controls_inference_total_microunits == 62779
    assert (tmp_path / "runtime.json").read_bytes() == stored
    now[0] = 3700.0
    with pytest.raises(ValueError, match="expired"):
        controlled_runtime.arm_inference_window(tmp_path, json.loads(stored))
    assert (tmp_path / "runtime.json").read_bytes() == stored


def test_expired_before_reservation_makes_no_call_or_reservation(ledger, monkeypatch):
    funded(ledger)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 100)
    ledger.clock = lambda: 100
    calls = []
    with (
        operation(ledger, CONTROL_SCOPE, "expired"),
        pytest.raises(ControlError, match="inference_window_expired"),
    ):
        model_call(lambda: calls.append(1), "hello", 10, lambda _: (2, 3))
    assert not calls and ledger.summary()["attempts"] == 0


def test_amount_only_restart_disables_deadline_not_ceiling(monkeypatch, tmp_path):
    manifest = {"amount_only_budget": {"total_microunits": 10}}
    monkeypatch.setattr(settings, "controls_inference_window_seconds", 7200)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 1)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 999)
    assert controlled_runtime.arm_inference_window(tmp_path, manifest) == manifest
    assert settings.controls_inference_expires_at == 0
    assert settings.controls_inference_window_seconds == 0
    assert settings.controls_inference_total_microunits == 10
    assert not (tmp_path / "runtime.json").exists()


def test_no_deadline_model_stub_still_stops_at_cumulative_cap(ledger, monkeypatch):
    funded(ledger)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 0)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 10000)
    calls = []
    with operation(ledger, CONTROL_SCOPE, "amount-only-first"):
        assert (
            model_call(lambda: calls.append(1) or "stub", "hello", 10, lambda _: (2, 3)) == "stub"
        )
    # Move to another accounting period: no new cumulative allowance appears.
    summary = ledger.summary()
    spent = summary["consumed"]["microunits"]
    assert spent > 0
    ledger.reserve("held", "unknown", CONTROL_SCOPE, Amount(microunits=10000 - spent), "model")
    ledger.settle("held", None)
    ledger.clock = lambda: 10**10
    with (
        operation(ledger, CONTROL_SCOPE, "amount-only-next"),
        pytest.raises(ControlError, match="budget_exhausted"),
    ):
        model_call(lambda: calls.append(2), "hello", 10, lambda _: (2, 3))
    assert calls == [1]
    assert ledger.summary()["reserved"]["microunits"] == 10000 - spent


def test_deadline_crossed_after_reservation_releases_only_unsent_attempt(ledger, monkeypatch):
    funded(ledger)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 101)
    now = [100.0]
    ledger.clock = lambda: now[0]
    checks = []

    def guard():
        checks.append(1)
        if len(checks) == 2:
            now[0] = 101

    calls = []
    with (
        operation(ledger, CONTROL_SCOPE, "crossed", guard),
        pytest.raises(ControlError, match="inference_window_expired"),
    ):
        model_call(lambda: calls.append(1), "hello", 10, lambda _: (2, 3))
    summary = ledger.summary()
    assert not calls and summary["states"]["settled"] == 1
    assert summary["reserved"]["tokens"] == summary["consumed"]["tokens"] == 0


@pytest.mark.parametrize("timeout", [False, True])
def test_already_sent_result_settles_or_stays_unknown_after_deadline(ledger, monkeypatch, timeout):
    funded(ledger)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 101)
    now = [100.0]
    ledger.clock = lambda: now[0]

    def send():
        now[0] = 102
        if timeout:
            raise TimeoutError("lost response")
        return {"ok": True}

    with operation(ledger, CONTROL_SCOPE, "sent"):
        if timeout:
            with pytest.raises(TimeoutError):
                model_call(send, "hello", 10, lambda _: (2, 3))
        else:
            assert model_call(send, "hello", 10, lambda _: (2, 3)) == {"ok": True}
    summary = ledger.summary()
    if timeout:
        assert summary["states"]["unknown"] == 1 and summary["reserved"]["tokens"] > 0
    else:
        assert summary["states"]["settled"] == 1 and summary["consumed"]["tokens"] == 5


def test_one_time_budget_counts_old_period_cost_and_unknown_holds(ledger, monkeypatch):
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 10)
    ledger.reserve("a", "old", CONTROL_SCOPE, Amount(microunits=6), "model")
    ledger.settle("a", Amount(microunits=6))
    ledger.clock = lambda: 86500
    ledger.reserve("b", "unknown", CONTROL_SCOPE, Amount(microunits=4), "model")
    ledger.settle("b", None)
    with pytest.raises(ControlError, match="budget_exhausted"):
        ledger.reserve("c", "new", CONTROL_SCOPE, Amount(microunits=1), "model")
    summary = ledger.summary()
    assert summary["consumed"]["microunits"] == 6 and summary["reserved"]["microunits"] == 4


def test_one_time_cap_reservations_share_atomic_sqlite_transaction(ledger, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(settings, "controls_inference_total_microunits", 70)

    def reserve(index):
        try:
            ledger.reserve(str(index), str(index), CONTROL_SCOPE, Amount(microunits=50), "model")
            return "reserved"
        except ControlError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, [1, 2]))
    assert sorted(results) == ["budget_exhausted", "reserved"]
    assert ledger.summary()["reserved"]["microunits"] == 50


def test_two_hour_pending_window_arms_once_with_approved_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "controls_inference_window_seconds", 3600)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 62779)
    monkeypatch.setattr(controlled_runtime.time, "time", lambda: 100)
    manifest = {
        "schema": 1,
        "pending_authorization": {
            "id": "approved-new-grant",
            "seconds": 7200,
            "total_microunits": 148223,
        },
    }
    armed = controlled_runtime.arm_inference_window(tmp_path, manifest)
    assert armed["inference_window"] == {
        "started": 100,
        "expires": 7300,
        "total_microunits": 148223,
        "authorization_id": "approved-new-grant",
    }
    assert "pending_authorization" not in armed
    monkeypatch.setattr(controlled_runtime.time, "time", lambda: 200)
    restarted = controlled_runtime.arm_inference_window(tmp_path, armed)
    assert restarted == armed
    monkeypatch.setattr(controlled_runtime.time, "time", lambda: 7300)
    with pytest.raises(ValueError, match="expired"):
        controlled_runtime.arm_inference_window(tmp_path, armed)
