# SPDX-License-Identifier: AGPL-3.0-only
"""Fixed short/week quota candidates: isolated ledger and model callable only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from app.config import settings
from app.controls.contracts import Amount, ControlError, Limits, ModelQuotas, Scope
from app.controls.ledger import Ledger
from app.controls.runtime import model_call, operation
from conftest import CONTROL_SCOPE as SCOPE
from conftest import controls_policy


def quotas(**changes):
    return ModelQuotas(
        **{
            "short_period_seconds": 21600,
            "short_anchor_utc": 57600,
            "short_microunits": 100,
            "week_anchor_utc": 316800,
            "week_microunits": 150,
            **changes,
        }
    )


def install(ledger, **changes):
    large = Limits(tokens=10**8, microunits=10**8, runs=10000, wall_ms=10**8)
    p = controls_policy(
        version="quota-v1",
        deployment=large,
        institution=large,
        classroom=large,
        learner=large,
        model_quotas=quotas(**changes),
    )
    ledger.update_policy(p)
    return p


def spend(ledger, name, amount, scope=SCOPE):
    ledger.reserve(name, name, scope, Amount(microunits=amount), "model")
    ledger.settle(name, Amount(microunits=amount))


@pytest.fixture
def week_start(ledger, monkeypatch):
    # Monday 2026-10-05 00:00 Asia/Shanghai.
    now = datetime(2026, 10, 4, 16, tzinfo=UTC).timestamp()
    ledger.clock = lambda: now
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 10**8)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 0)
    return now


def test_short_refresh_preserves_week_and_history(ledger, week_start):
    install(ledger)
    spend(ledger, "first", 100)
    ledger.clock = lambda: week_start + 21600 - 0.001
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "too-early", 1)
    ledger.clock = lambda: week_start + 21600
    spend(ledger, "second", 50)
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "week-full", 1)
    assert ledger.summary()["consumed"]["microunits"] == 150
    ledger.clock = lambda: week_start + 604800
    spend(ledger, "new-week", 100)
    assert ledger.summary()["consumed"]["microunits"] == 250


def test_unknown_carries_both_boundaries_and_late_settlement_uses_original_period(
    ledger, week_start
):
    install(ledger)
    ledger.reserve("unknown", "original", SCOPE, Amount(microunits=100), "model")
    ledger.settle("unknown", None)
    ledger.clock = lambda: week_start + 604800
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "held", 1)
    ledger.settle("unknown", Amount(microunits=30))
    spend(ledger, "after-reconcile", 100)
    assert ledger.summary()["consumed"]["microunits"] == 130
    assert ledger.summary()["attempts"] == 2


def test_preexisting_usage_counts_when_quotas_enabled(ledger, week_start):
    spend(ledger, "before-enabling", 90)
    install(ledger)
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "not-a-fresh-allowance", 11)
    spend(ledger, "fits", 10)


def test_cumulative_cap_still_blocks_after_week_refresh(ledger, week_start, monkeypatch):
    install(ledger)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 120)
    spend(ledger, "old", 100)
    ledger.clock = lambda: week_start + 604800
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "not-new-funding", 21)
    spend(ledger, "remaining", 20)


def test_atomic_quota_shared_by_classes_and_dedup(ledger, week_start):
    install(ledger)

    def reserve(index):
        try:
            ledger.reserve(
                str(index),
                str(index),
                Scope(SCOPE.deployment, "i", str(index), "l"),
                Amount(microunits=60),
                "model",
            )
            return "reserved"
        except ControlError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, [1, 2])) == ["budget_exhausted", "reserved"]
    assert ledger.summary()["reserved"]["microunits"] == 60


def test_independent_deployment_and_existing_scope_limit(ledger, week_start):
    p = install(ledger)
    spend(ledger, "a", 100)
    spend(ledger, "b", 100, Scope("another-deployment", "i", "c", "l"))
    ledger.update_policy(
        p.model_copy(update={"version": "quota-v2", "learner": Limits(microunits=5)})
    )
    ledger.clock = lambda: week_start + 86400
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "learner-limit", 6)


def test_weekly_race_and_policy_version_restart_do_not_reset_usage(ledger, week_start):
    p = install(ledger, short_microunits=200)
    spend(ledger, "earlier-period", 60)
    ledger.clock = lambda: week_start + 21600
    ledger.update_policy(p.model_copy(update={"version": "quota-v2"}))
    restarted = Ledger(ledger.engine, clock=ledger.clock)

    def reserve(index):
        try:
            restarted.reserve(str(index), str(index), SCOPE, Amount(microunits=60), "model")
            return "reserved"
        except ControlError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, [1, 2])) == ["budget_exhausted", "reserved"]
    assert restarted.summary()["consumed"]["microunits"] == 60
    assert restarted.summary()["reserved"]["microunits"] == 60


def test_stub_dispatch_settlement_and_block_before_second_call(ledger, week_start):
    install(ledger, short_microunits=3000, week_microunits=5000)
    calls = []
    with operation(ledger, SCOPE, "first"):
        assert (
            model_call(lambda: calls.append(1) or "stub", "input", 10, lambda _: (1000, 500))
            == "stub"
        )
    with operation(ledger, SCOPE, "second"), pytest.raises(ControlError, match="budget_exhausted"):
        model_call(lambda: calls.append(2), "input", 10, lambda _: (1, 1))
    assert calls == [1]


def test_daily_candidate_boundary_and_idempotent_reservation(ledger, week_start):
    install(ledger, short_period_seconds=86400)
    ledger.reserve("same", "same", SCOPE, Amount(microunits=100), "model")
    ledger.settle("same", Amount(microunits=100))
    ledger.reserve("same", "same", SCOPE, Amount(microunits=100), "model")
    ledger.clock = lambda: week_start + 86400
    spend(ledger, "tomorrow", 50)
    assert ledger.summary()["attempts"] == 2


def test_approved_local_values_preserve_history_and_funding(ledger, week_start, monkeypatch):
    # Exact October 11 authorization: USD5 additional, USD1 / six hours,
    # USD5 / week. These are isolated ledger amounts, not provider requests.
    spend(ledger, "earlier-this-week", 114475)
    ledger.clock = lambda: week_start + 21600
    spend(ledger, "current-short-period", 17362)
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 5148223)
    install(ledger, short_microunits=1000000, week_microunits=5000000)
    spend(ledger, "short-remainder", 982638)
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "short-full", 1)
    for index in range(2, 5):
        ledger.clock = lambda index=index: week_start + index * 21600
        spend(ledger, f"later-short-{index}", 1000000)
    ledger.clock = lambda: week_start + 5 * 21600
    spend(ledger, "weekly-remainder", 885525)
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "week-full", 1)
    assert ledger.summary()["consumed"]["microunits"] == 5000000
    ledger.clock = lambda: week_start + 604800
    spend(ledger, "last-funded-balance", 148223)
    with pytest.raises(ControlError, match="budget_exhausted"):
        spend(ledger, "no-automatic-funding", 1)
    assert ledger.summary()["consumed"]["microunits"] == 5148223


@pytest.mark.parametrize(
    "change",
    [
        {"short_period_seconds": 0},
        {"short_period_seconds": 90000},
        {"short_microunits": -1},
        {"week_microunits": None},
    ],
)
def test_invalid_candidate_rejected(change):
    with pytest.raises(ValueError):
        quotas(**change)
