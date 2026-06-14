"""
Provider seam: provider selection + per-provider tier mapping (no network).

Core selects a provider by the PROVIDER key and maps the provider-agnostic
fast/strong tiers to concrete models via per-provider config. None of this
touches the network or constructs a real SDK client.
"""
from __future__ import annotations

import importlib

import pytest

from app.agent.llm import (
    AnthropicProvider,
    BedrockProvider,
    OpenAICompatProvider,
    Provider,
    provider_class,
)


# ── provider selection ────────────────────────────────────────────────────────

def test_provider_class_selection():
    assert provider_class("openai_compatible") is OpenAICompatProvider
    assert provider_class("anthropic") is AnthropicProvider
    assert provider_class("bedrock") is BedrockProvider


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        provider_class("does_not_exist")


def test_get_provider_honors_PROVIDER(monkeypatch):
    """get_provider() constructs the class named by PROVIDER. Use the stub
    (bedrock) so no SDK/network is required to prove selection."""
    import app.config as config_mod
    import app.agent.llm as llm_mod
    monkeypatch.setenv("PROVIDER", "bedrock")
    # Rebuild settings from env, then re-point the llm module at it.
    new_settings = config_mod.Settings()
    monkeypatch.setattr(config_mod, "settings", new_settings)
    monkeypatch.setattr(llm_mod, "settings", new_settings)
    prov = llm_mod.get_provider()
    assert isinstance(prov, BedrockProvider)
    assert prov.name == "bedrock"


# ── tier mapping is provider-agnostic policy, per-provider config ─────────────

def _settings(monkeypatch, **env):
    import app.config as config_mod
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return config_mod.Settings()


def test_openai_tier_mapping(monkeypatch):
    s = _settings(monkeypatch, PROVIDER="openai_compatible",
                  MODEL_FAST="fastmodel", MODEL_STRONG="strongmodel")
    assert s.model_tiers == {"fast": "fastmodel", "strong": "strongmodel"}


def test_single_model_endpoint_collapses_tiers(monkeypatch):
    """A single-model self-hosted endpoint maps fast and strong to one model."""
    s = _settings(monkeypatch, PROVIDER="openai_compatible",
                  MODEL_FAST="llama3.2", MODEL_STRONG="llama3.2")
    assert s.model_tiers["fast"] == s.model_tiers["strong"] == "llama3.2"


def test_anthropic_tier_mapping(monkeypatch):
    s = _settings(monkeypatch, PROVIDER="anthropic",
                  ANTHROPIC_MODEL_FAST="claude-haiku-4-5-20251001",
                  ANTHROPIC_MODEL_STRONG="claude-sonnet-4-6")
    assert s.model_tiers == {"fast": "claude-haiku-4-5-20251001",
                             "strong": "claude-sonnet-4-6"}


def test_bedrock_nova_tier_mapping(monkeypatch):
    """The documented Bedrock stub still maps tiers to Amazon Nova models."""
    s = _settings(monkeypatch, PROVIDER="bedrock")
    assert s.model_tiers == {"fast": "amazon.nova-lite-v1:0",
                             "strong": "amazon.nova-pro-v1:0"}


def test_bedrock_stub_raises_on_call():
    with pytest.raises(NotImplementedError):
        BedrockProvider().json(role="planner", tier="fast", system="s", user="u")


# ── the seam is a Protocol a stub satisfies (no network in the whole suite) ───

def test_stub_satisfies_provider_protocol():
    class StubProvider:
        name = "stub"

        def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
            return {"ok": True, "tier": tier}

    stub = StubProvider()
    assert isinstance(stub, Provider)   # runtime-checkable structural match
    assert stub.json(role="planner", tier="strong", system="s", user="u")["tier"] == "strong"
