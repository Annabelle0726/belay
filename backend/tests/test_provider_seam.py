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

def test_openai_compatible_targets_configured_base_url(monkeypatch):
    """Zero-external-API wiring: PROVIDER=openai_compatible + OPENAI_BASE_URL routes
    the client at the configured (local) endpoint. Construction only — no network."""
    import app.config as config_mod
    import app.agent.llm as llm_mod
    monkeypatch.setenv("PROVIDER", "openai_compatible")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ollama")
    s = config_mod.Settings()
    monkeypatch.setattr(config_mod, "settings", s)
    monkeypatch.setattr(llm_mod, "settings", s)
    prov = llm_mod.get_provider()
    assert isinstance(prov, OpenAICompatProvider)
    assert str(prov._client.base_url).rstrip("/") == "http://localhost:11434/v1"


# ── thinking is a model capability (default off for openai_compatible) ────────

class _FakeMsg:
    content = '{"ok": true}'


class _FakeChoice:
    message = _FakeMsg()


class _FakeResp:
    choices = [_FakeChoice()]
    usage = None


class _Completions:
    def __init__(self, rec):
        self._rec = rec

    def create(self, **kwargs):
        self._rec["kwargs"] = kwargs
        return _FakeResp()


class _Chat:
    def __init__(self, rec):
        self.completions = _Completions(rec)


class _RecorderClient:
    """Records the kwargs passed to chat.completions.create; no network."""

    def __init__(self):
        self.rec: dict = {}
        self.chat = _Chat(self.rec)


def _openai_provider_with_recorder(monkeypatch, settings_obj):
    import app.agent.llm as llm_mod
    monkeypatch.setattr(llm_mod, "settings", settings_obj)
    prov = OpenAICompatProvider.__new__(OpenAICompatProvider)  # bypass real client init
    prov._client = _RecorderClient()
    return prov


def test_openai_compatible_omits_thinking_by_default(monkeypatch):
    """Default: NO thinking/reasoning param — works against ordinary non-reasoning
    local models (llama3.2/mistral/qwen2.5)."""
    import app.config as config_mod
    s = config_mod.Settings()                      # OPENAI_REASONING unset -> False
    prov = _openai_provider_with_recorder(monkeypatch, s)
    # Even with a per-call reasoning_effort (the escalation lever), nothing is sent.
    prov.json(role="reasoner", tier="strong", system="s", user="u", reasoning_effort="medium")
    kwargs = prov._client.rec["kwargs"]
    assert "extra_body" not in kwargs              # no reasoning/thinking parameter
    assert "messages" in kwargs                    # (sanity: real create path recorded)


def test_openai_compatible_sends_thinking_when_enabled(monkeypatch):
    """Opt-in (OPENAI_REASONING=1): reasoning_effort is sent for a reasoning model."""
    import app.config as config_mod
    monkeypatch.setenv("OPENAI_REASONING", "1")
    s = config_mod.Settings()
    prov = _openai_provider_with_recorder(monkeypatch, s)
    prov.json(role="reasoner", tier="strong", system="s", user="u", reasoning_effort="high")
    assert prov._client.rec["kwargs"].get("extra_body") == {"reasoning_effort": "high"}


def test_openai_compatible_capability_default_is_off():
    import app.config as config_mod
    assert config_mod.Settings().openai_reasoning is False


def test_stub_satisfies_provider_protocol():
    class StubProvider:
        name = "stub"

        def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
            return {"ok": True, "tier": tier}

    stub = StubProvider()
    assert isinstance(stub, Provider)   # runtime-checkable structural match
    assert stub.json(role="planner", tier="strong", system="s", user="u")["tier"] == "strong"
