# SPDX-License-Identifier: AGPL-3.0-only
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app.agent import telemetry
from app.agent.injection_guard import InjectionGuard
from app.agent.llm import AnthropicProvider, OpenAICompatProvider
from app.config import settings
from app.controls.contracts import ControlError, Limits
from app.controls.ledger import attempts
from app.controls.runtime import operation
from app.core import runner
from conftest import CONTROL_SCOPE as SCOPE
from conftest import controls_policy as policy


def response(text='{"ok": true}', usage=True):
    return NS(
        choices=[NS(message=NS(content=text))],
        usage=NS(prompt_tokens=10, completion_tokens=5) if usage else None,
    )


def provider(responses):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    value = OpenAICompatProvider.__new__(OpenAICompatProvider)
    value._client = NS(chat=NS(completions=NS(create=create)))
    return value, calls


def invoke(value):
    return value.json(role="planner", tier="fast", system="s", user="u", max_tokens=10)


def funded(ledger):
    ledger.update_policy(
        policy(version="v2", deployment=Limits(tokens=100000, runs=5, wall_ms=10000))
    )


def test_invalid_json_accounts_both_attempts(ledger):
    funded(ledger)
    value, calls = provider([response("not json"), response()])
    meter = telemetry.UsageMeter()
    token = telemetry.set_meter(meter)
    try:
        with operation(ledger, SCOPE, "op"):
            assert invoke(value) == {"ok": True}
    finally:
        telemetry.reset_meter(token)
    assert len(calls) == 2
    assert ledger.summary()["consumed"]["tokens"] == 30
    assert meter.by_component()["planner"]["calls"] == 2


def test_timeout_retains_hold_without_retry(ledger):
    funded(ledger)
    value, calls = provider([TimeoutError("response lost"), response()])
    with operation(ledger, SCOPE, "op"), pytest.raises(TimeoutError):
        invoke(value)
    assert len(calls) == 1
    assert ledger.summary()["states"]["unknown"] == 1
    assert ledger.summary()["reserved"]["tokens"] > 0


def test_missing_usage_is_unknown(ledger):
    funded(ledger)
    value, _ = provider([response(usage=False)])
    with operation(ledger, SCOPE, "op"):
        invoke(value)
    assert ledger.summary()["states"]["unknown"] == 1


def test_exhaustion_stops_before_sdk_and_guard_does_not_swallow(ledger, monkeypatch):
    value, calls = provider([response()])
    monkeypatch.setattr(settings, "injection_guard_enabled", True)
    guard = InjectionGuard()
    guard._initialized, guard._llm = True, value
    with operation(ledger, SCOPE, "op"), pytest.raises(ControlError, match="budget_exhausted"):
        guard.check("test")
    assert calls == []


def test_enforced_without_trusted_context_blocks_model_and_runner(monkeypatch):
    monkeypatch.setattr(settings, "controls_mode", "enforced")
    value, calls = provider([response()])
    with pytest.raises(ControlError, match="verified_execution_required"):
        invoke(value)
    with pytest.raises(ControlError, match="verified_execution_required"):
        runner.run_python("print(1)")
    assert calls == []


def test_runner_is_charged_and_denial_prevents_execution(ledger, monkeypatch):
    funded(ledger)
    calls = []

    def execute(*args, **kwargs):
        calls.append(1)
        return runner.RunnerResult(True, 0, "", "", False, 50.0, None)

    monkeypatch.setattr(runner, "_run_python", execute)
    with operation(ledger, SCOPE, "op"):
        runner.run_python("pass", wall_seconds=1)
    assert ledger.summary()["consumed"]["runs"] == 1
    ledger.update_policy(policy(version="v3", deployment=Limits(runs=1)))
    with operation(ledger, SCOPE, "op2"), pytest.raises(ControlError):
        runner.run_python("pass", wall_seconds=1)
    assert len(calls) == 1


def test_anthropic_effective_thinking_limit_and_failed_json_charged(ledger, monkeypatch):
    funded(ledger)
    monkeypatch.setattr(settings, "anthropic_thinking", True)
    monkeypatch.setattr(settings, "anthropic_thinking_budget", 2048)
    value = AnthropicProvider.__new__(AnthropicProvider)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return NS(
            content=[NS(type="text", text="invalid")], usage=NS(input_tokens=5, output_tokens=10)
        )

    value._client = NS(messages=NS(create=create))
    with operation(ledger, SCOPE, "op"), pytest.raises(ValueError):
        invoke(value)
    assert calls[0]["max_tokens"] == 2560
    assert ledger.summary()["consumed"]["tokens"] == 15
    with ledger.transaction() as conn:
        row = conn.execute(select(attempts)).mappings().one()
    assert row["reserved"]["tokens"] >= 2560
    assert "invalid" not in str(row)


def test_sdk_retry_disabled():
    from app.agent.llm import OpenAICompatProvider

    assert OpenAICompatProvider()._client.max_retries == 0
