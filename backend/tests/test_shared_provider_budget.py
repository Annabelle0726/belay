# SPDX-License-Identifier: AGPL-3.0-only
"""Real adapters, fake SDK responses, and independent coordinator processes."""

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine

from app.agent import llm, planner, reasoner, self_eval, telemetry
from app.config import settings
from app.controls.contracts import Amount, ControlError, Limits, ModelQuotas
from app.controls.ledger import Ledger, metadata
from app.controls.runtime import operation
from conftest import CONTROL_SCOPE as SCOPE
from conftest import controls_policy
from tests.test_provider_capabilities import sdk


def budget(ledger, short=3000, week=5000, **extra):
    large = Limits(tokens=10**7, microunits=10**7, runs=1000, wall_ms=10**7)
    policy = controls_policy(
        version="mixed-v1",
        deployment=large,
        institution=large,
        classroom=large,
        learner=large,
        model_quotas=ModelQuotas(
            short_period_seconds=3600,
            short_anchor_utc=0,
            short_microunits=short,
            week_anchor_utc=0,
            week_microunits=week,
        ),
        **extra,
    )
    ledger.update_policy(policy)


def reply(provider, prompt=1000, completion=100):
    usage = NS(
        prompt_tokens=prompt,
        completion_tokens=completion,
        input_tokens=prompt,
        output_tokens=completion,
    )
    if provider == "anthropic":
        return NS(content=[NS(type="text", text='{"ok":true}')], usage=usage)
    return NS(choices=[NS(message=NS(content='{"ok":true}'))], usage=usage)


def call(provider, role="planner"):
    return provider.json(role=role, tier="fast", system="s", user="u", max_tokens=100)


def test_mixed_provider_model_switches_share_short_week_and_cumulative(ledger, monkeypatch):
    budget(ledger)
    monkeypatch.setattr(settings, "llm_billing_mode", "metered")
    monkeypatch.setattr(settings, "controls_inference_total_microunits", 7000)
    monkeypatch.setattr(settings, "controls_inference_expires_at", 0)
    monkeypatch.setattr(settings, "anthropic_thinking", False)
    responses = [
        reply(p)
        for p in ["openai_compatible", "anthropic", "anthropic", "openai_compatible", "anthropic"]
    ]
    calls, _ = sdk(monkeypatch, responses)

    def invoke(provider, name, model):
        monkeypatch.setattr(settings, "provider", name)
        monkeypatch.setattr(
            settings,
            "openai_model_fast" if name == "openai_compatible" else "anthropic_model_fast",
            model,
        )
        with operation(ledger, SCOPE, f"{name}-{len(calls)}"):
            return call(provider())

    invoke(llm.OpenAICompatProvider, "openai_compatible", "model-a")
    invoke(llm.AnthropicProvider, "anthropic", "model-b")
    assert ledger.summary()["consumed"]["microunits"] == 2400
    with pytest.raises(ControlError, match="budget_exhausted"):
        invoke(llm.OpenAICompatProvider, "openai_compatible", "different-model")
    assert len(calls) == 2
    ledger.clock = lambda: 3600
    invoke(llm.AnthropicProvider, "anthropic", "another-model")
    invoke(llm.OpenAICompatProvider, "openai_compatible", "third-model")
    ledger.clock = lambda: 7200
    with pytest.raises(ControlError, match="budget_exhausted"):
        invoke(llm.AnthropicProvider, "anthropic", "model-c")
    assert len(calls) == 4  # Weekly ceiling, despite a new short bucket/model.
    ledger.clock = lambda: 604800
    invoke(llm.AnthropicProvider, "anthropic", "model-c")
    with pytest.raises(ControlError, match="budget_exhausted"):
        invoke(llm.OpenAICompatProvider, "openai_compatible", "model-d")
    assert len(calls) == 5 and ledger.summary()["consumed"]["microunits"] == 6000


@pytest.mark.parametrize("mode", ["metered", "", "unknown"])
def test_missing_price_or_billing_mode_never_dispatches(ledger, monkeypatch, mode):
    budget(ledger, input_price=0, output_price=0)
    monkeypatch.setattr(settings, "llm_billing_mode", mode)
    calls, _ = sdk(monkeypatch, [reply("openai_compatible")])
    with operation(ledger, SCOPE, "no-price"), pytest.raises(ControlError):
        call(llm.OpenAICompatProvider())
    assert not calls and ledger.summary()["attempts"] == 0


def test_explicit_unmetered_retains_tokens_and_scoped_limits(ledger, monkeypatch):
    budget(ledger, input_price=0, output_price=0)
    monkeypatch.setattr(settings, "llm_billing_mode", "unmetered")
    calls, _ = sdk(monkeypatch, [reply("openai_compatible", 10, 5)])
    with operation(ledger, SCOPE, "self-hosted"):
        call(llm.OpenAICompatProvider())
    summary = ledger.summary()
    assert summary["consumed"]["tokens"] == 15 and summary["consumed"]["microunits"] == 0
    with ledger.transaction() as conn:
        policy = ledger.policy(conn)
    ledger.update_policy(
        policy.model_copy(update={"version": "free-token-cap", "learner": Limits(tokens=15)})
    )
    with operation(ledger, SCOPE, "still-limited"), pytest.raises(ControlError):
        call(llm.OpenAICompatProvider())
    assert len(calls) == 1


def test_real_components_and_revision_each_accounted(ledger, monkeypatch):
    budget(ledger, short=1000000, week=2000000)
    monkeypatch.setattr(settings, "llm_billing_mode", "metered")
    calls, _ = sdk(monkeypatch, [reply("openai_compatible", 10, 5) for _ in range(4)])
    provider = llm.OpenAICompatProvider()
    ctx = {
        "mode": "study",
        "exercise": {"id": "ds-foundations", "concept": "groupby"},
        "attempt_signals": {},
        "current_functional_model": "",
        "last_result": {},
        "dialogue": [],
    }
    meter = telemetry.UsageMeter()
    token = telemetry.set_meter(meter)
    try:
        with operation(ledger, SCOPE, "components"):
            plan = planner.plan(ctx, provider)
            draft = reasoner.respond(ctx, plan, provider)
            critique = self_eval.evaluate(ctx, plan, draft, provider)
            reasoner.respond(ctx, plan, provider, critique={**critique, "needs_revision": True})
    finally:
        telemetry.reset_meter(token)
    assert len(calls) == 4
    assert {k: v["calls"] for k, v in meter.by_component().items()} == {
        "planner": 1,
        "reasoner": 2,
        "self_eval": 1,
    }
    assert ledger.summary()["consumed"]["microunits"] == 80


def _reserve_process(url, attempt):
    engine = create_engine(url)
    ledger = Ledger(engine, lambda: 100)
    try:
        ledger.reserve(attempt, attempt, SCOPE, Amount(microunits=60), "model")
        return attempt, "reserved"
    except ControlError as exc:
        return attempt, exc.code
    finally:
        engine.dispose()


def _settle_process(url, attempt):
    engine = create_engine(url)
    ledger = Ledger(engine, lambda: 100)
    try:
        ledger.settle(attempt, Amount(microunits=40))
        ledger.settle(attempt, Amount(microunits=40))
    finally:
        engine.dispose()


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_independent_processes_share_reservations_and_idempotent_settlement(tmp_path, backend):
    url = f"sqlite:///{tmp_path / 'shared-processes.sqlite3'}"
    if backend == "postgres":
        url = os.environ.get("CONTROL_TEST_DATABASE_URL", "")
        if not url:
            pytest.skip("requires isolated CONTROL_TEST_DATABASE_URL PostgreSQL database")
    engine = create_engine(url)
    if backend == "postgres":
        assert engine.dialect.name == "postgresql"
        metadata.drop_all(engine)  # Only the explicitly selected disposable test DB.
    ledger = Ledger(engine, lambda: 100)
    ledger.initialize(
        controls_policy(
            model_quotas=ModelQuotas(
                short_period_seconds=3600,
                short_anchor_utc=0,
                short_microunits=100,
                week_anchor_utc=0,
                week_microunits=100,
            )
        )
    )
    with ProcessPoolExecutor(2, mp_context=mp.get_context("spawn")) as pool:
        results = list(pool.map(_reserve_process, [url] * 2, ["provider-a", "provider-b"]))
        assert sorted(result for _, result in results) == ["budget_exhausted", "reserved"]
        winner = next(name for name, result in results if result == "reserved")
        loser = next(name for name, result in results if result != "reserved")
        pool.submit(_settle_process, url, winner).result()
        assert pool.submit(_reserve_process, url, loser).result()[1] == "reserved"
    assert ledger.summary()["consumed"]["microunits"] == 40
    assert ledger.summary()["reserved"]["microunits"] == 60
    engine.dispose()
