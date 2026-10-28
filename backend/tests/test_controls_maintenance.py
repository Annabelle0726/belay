# SPDX-License-Identifier: AGPL-3.0-only
import json

import pytest

from app.controls.admission import Admission
from app.controls.cli import main
from app.controls.contracts import Amount, ControlError, Limits
from app.controls.maintenance import reconcile, snapshot, unresolved
from conftest import CONTROL_SCOPE as SCOPE
from conftest import controls_policy as policy


def test_reconciliation_separates_usage_from_termination(ledger):
    ledger.reserve("a", "op", SCOPE, Amount(tokens=800), "model")
    ledger.settle("a", None)
    service = Admission(ledger)
    slot = service.acquire_slot(SCOPE, "op", "model")
    service.release_slot(slot, stopped=False)
    reconcile(ledger, "a", "a" * 32, action="settle_attempt", actual=Amount(tokens=500))
    summary = snapshot(ledger)
    assert summary["consumed"]["tokens"] == 500
    assert summary["slots"]["model"]["unknown"] == 1
    reconcile(ledger, "op", "b" * 32, action="confirm_stopped")
    assert snapshot(ledger)["slots"]["model"]["unknown"] == 0
    assert unresolved(ledger) == []
    with pytest.raises(ControlError, match="reconciliation_conflict"):
        reconcile(ledger, "a", "a" * 32, action="settle_attempt", actual=Amount())


def test_overrun_acknowledgement_preserves_usage(ledger):
    ledger.reserve("a", "op", SCOPE, Amount(tokens=5), "model")
    ledger.settle("a", Amount(tokens=10))
    reconcile(ledger, "a", "a" * 32, action="acknowledge_overrun")
    ledger.reserve("b", "op", SCOPE, Amount(tokens=1), "model")
    summary = snapshot(ledger)
    assert summary["states"]["overrun"] == 1
    assert summary["consumed"]["tokens"] == 10
    ledger.update_policy(policy(version="v2", deployment=Limits(tokens=10)))
    with pytest.raises(ControlError, match="budget_exhausted"):
        ledger.reserve("c", "op", SCOPE, Amount(tokens=1), "model")


def test_summary_expiry_and_denial_counts(ledger):
    service = Admission(ledger)
    service.submit(SCOPE, "op", "a" * 64, "b" * 32, 10, Amount(tokens=800))
    with pytest.raises(ControlError):
        ledger.reserve("a", "op", SCOPE, Amount(tokens=800), "model")
    ledger.clock = lambda: 500.0
    summary = snapshot(ledger)
    assert summary["reserved"]["tokens"] == 0
    assert summary["queue"]["depth"] == 0
    assert summary["rejections"]["budget_exhausted"] == 1


def test_operator_cli_requires_database_credentials_and_exposes_no_http_route(
    ledger, monkeypatch, capsys
):
    monkeypatch.setenv("CONTROLS_DATABASE_URL", str(ledger.engine.url))
    assert main(["summary"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["policy_version"] == "test-v1"
    monkeypatch.delenv("CONTROLS_DATABASE_URL")
    with pytest.raises(SystemExit):
        main(["summary"])
