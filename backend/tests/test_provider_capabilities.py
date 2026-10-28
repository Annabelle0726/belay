# SPDX-License-Identifier: AGPL-3.0-only
"""Actual adapters, simulated SDKs; every attempt still crosses model_call."""

import sys
from types import SimpleNamespace as NS

import pytest

from app.agent import llm
from app.config import settings
from app.controls.contracts import Limits
from app.controls.runtime import operation
from conftest import CONTROL_SCOPE


def funded(ledger):
    with ledger.transaction() as conn:
        policy = ledger.policy(conn)
    ledger.update_policy(
        policy.model_copy(
            update={"version": "capability-test", "deployment": Limits(tokens=1000000)}
        )
    )


def response(text='{"ok":true}', usage=True):
    return NS(
        choices=[NS(message=NS(content=text, reasoning_content='{"private":true}'))],
        usage=NS(prompt_tokens=10, completion_tokens=5) if usage else None,
    )


def sdk(monkeypatch, responses):
    calls, constructors = [], []

    def create(**kwargs):
        calls.append(kwargs)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    class Client:
        def __init__(self, **kwargs):
            constructors.append(kwargs)
            self.chat = NS(completions=NS(create=create))
            self.messages = NS(create=create)

    monkeypatch.setitem(sys.modules, "openai", NS(OpenAI=Client))
    monkeypatch.setitem(sys.modules, "anthropic", NS(Anthropic=Client))
    return calls, constructors


def invoke(provider):
    return provider.json(role="reasoner", tier="strong", system="test", user="test", max_tokens=100)


def test_thinking_capability_covers_format_fallback_and_json_repair(ledger, monkeypatch):
    funded(ledger)
    rejection = type("Rejected", (Exception,), {"status_code": 400})()
    calls, _ = sdk(monkeypatch, [rejection, response("not JSON"), response()])
    monkeypatch.setattr(settings, "openai_thinking_mode", "disabled")
    with operation(ledger, CONTROL_SCOPE, "capability"):
        assert invoke(llm.OpenAICompatProvider()) == {"ok": True}
    assert len(calls) == 3
    assert all(c["extra_body"]["thinking"] == {"type": "disabled"} for c in calls)
    summary = ledger.summary()
    assert summary["states"]["unknown"] == 1 and summary["states"]["settled"] == 2


def test_generic_openai_omits_opt_in_capability_and_can_disable_json_response_format(
    ledger, monkeypatch
):
    funded(ledger)
    calls, constructors = sdk(monkeypatch, [response()])
    monkeypatch.setattr(settings, "openai_thinking_mode", "")
    monkeypatch.setattr(settings, "openai_reasoning", False)
    monkeypatch.setattr(settings, "openai_response_format", "none")
    monkeypatch.setattr(settings, "llm_timeout_seconds", 9)
    with operation(ledger, CONTROL_SCOPE, "generic"):
        invoke(llm.OpenAICompatProvider())
    assert "extra_body" not in calls[0] and "response_format" not in calls[0]
    assert constructors[0]["timeout"] == 9 and constructors[0]["max_retries"] == 0


def test_final_content_only_never_releases_reasoning_as_an_answer(ledger, monkeypatch):
    funded(ledger)
    calls, _ = sdk(monkeypatch, [response(""), response("")])
    monkeypatch.setattr(settings, "openai_final_content_only", True)
    with operation(ledger, CONTROL_SCOPE, "reasoning"), pytest.raises(ValueError):
        invoke(llm.OpenAICompatProvider())
    assert len(calls) == 2 and ledger.summary()["consumed"]["tokens"] == 30


@pytest.mark.parametrize("adapter", [llm.OpenAICompatProvider, llm.AnthropicProvider])
@pytest.mark.parametrize("unknown", ["timeout", "missing_usage"])
def test_both_adapters_unknown_usage_retains_reservation_without_sdk_retry(
    ledger, monkeypatch, adapter, unknown
):
    funded(ledger)
    result = (
        response(usage=False)
        if adapter is llm.OpenAICompatProvider
        else NS(content=[NS(type="text", text='{"ok":true}')], usage=None)
    )
    calls, constructors = sdk(monkeypatch, [TimeoutError() if unknown == "timeout" else result])
    with operation(ledger, CONTROL_SCOPE, "unknown"):
        if unknown == "timeout":
            with pytest.raises(TimeoutError):
                invoke(adapter())
        else:
            assert invoke(adapter()) == {"ok": True}
    assert len(calls) == 1 and constructors[0]["max_retries"] == 0
    assert ledger.summary()["reserved"]["tokens"] > 0
    assert ledger.summary()["states"]["unknown"] == 1


def test_openai_capabilities_do_not_leak_to_anthropic_and_cache_tokens_are_counted(
    ledger, monkeypatch
):
    funded(ledger)
    calls, constructors = sdk(
        monkeypatch,
        [
            NS(
                content=[NS(type="thinking", text="private"), NS(type="text", text='{"ok":true}')],
                usage=NS(
                    input_tokens=6,
                    cache_creation_input_tokens=2,
                    cache_read_input_tokens=2,
                    output_tokens=5,
                ),
            )
        ],
    )
    monkeypatch.setattr(settings, "openai_thinking_mode", "disabled")
    monkeypatch.setattr(settings, "anthropic_thinking", True)
    monkeypatch.setattr(settings, "anthropic_thinking_budget", 2048)
    monkeypatch.setattr(settings, "llm_timeout_seconds", 7)
    with operation(ledger, CONTROL_SCOPE, "anthropic"):
        assert invoke(llm.AnthropicProvider()) == {"ok": True}
    assert "extra_body" not in calls[0] and "response_format" not in calls[0]
    assert calls[0]["thinking"]["type"] == "enabled" and calls[0]["max_tokens"] == 2560
    assert constructors[0]["timeout"] == 7
    assert ledger.summary()["consumed"]["tokens"] == 15
