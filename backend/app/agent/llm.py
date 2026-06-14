"""
The inference Provider seam.

Core calls a `Provider` (the `json(...)` method), never a concrete SDK. The
fast/strong TIER POLICY (which component runs on which tier) lives in core and is
provider-agnostic — the Planner and Self-Evaluator use the fast tier, the
Peer-Reasoner the strong tier. Only the tier->concrete-model mapping is
per-provider config (`settings.model_tiers`).

Providers:
  - OpenAICompatProvider (live, FIRST-CLASS, self-hosted): any OpenAI-compatible
    endpoint (Ollama / vLLM / a Jetstream2-hosted model / MESA AI-Verde) via a
    configurable base_url + model(s) + optional key. Needs NO Anthropic
    dependency, enabling a zero-external-API deployment.
  - AnthropicProvider (live, hosted convenience): wraps the Anthropic client.
  - BedrockProvider (documented STUB; not live): Amazon Nova tier mapping.

`Provider` is a Protocol with a single `json(...)` method so tests inject a
deterministic stub and exercise the whole loop with no network. `get_provider()`
(aka `get_llm()`) returns the configured provider.

INVARIANT: the provider seam carries NO governance decision. The inference choice
never changes the deterministic leak gate.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Protocol, runtime_checkable

from ..config import settings


@runtime_checkable
class Provider(Protocol):
    name: str

    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict: ...


# Back-compat alias (older imports referenced LLMClient).
LLMClient = Provider


def parse_json(text: str) -> dict | None:
    """Strip fences, then parse. Falls back to the first {...} block. This also
    tolerates reasoning models that prepend analysis before the final JSON."""
    clean = (text or "").strip()
    clean = re.sub(r"^```(?:json)?", "", clean).strip()
    clean = re.sub(r"```$", "", clean).strip()
    try:
        return json.loads(clean)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", clean)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _model_for(tier: str) -> str:
    tiers = settings.model_tiers
    return tiers.get(tier, tiers["fast"])


class OpenAICompatProvider:
    """Live, first-class self-hosted path: one OpenAI-compatible endpoint
    (`settings.openai_base_url`) serving all tiers (Ollama/vLLM/JS2/MESA)."""

    name = "openai_compatible"

    def __init__(self) -> None:
        from openai import OpenAI  # lazy import
        self._client = OpenAI(base_url=settings.openai_base_url,
                              api_key=settings.openai_api_key)

    def model_for(self, tier: str) -> str:
        return _model_for(tier)

    @staticmethod
    def _extract_text(resp) -> str:
        msg = resp.choices[0].message
        return (getattr(msg, "content", None)
                or getattr(msg, "reasoning_content", "")
                or "")

    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict:
        model = self.model_for(tier)
        kwargs: dict = dict(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=settings.llm_temperature,
            max_tokens=max_tokens,
        )
        # Per-call reasoning_effort (escalation lever) overrides the tier default;
        # the strong-tier default comes from config (empty = not sent).
        effort = reasoning_effort or (settings.reasoning_strong if tier == "strong" else "")
        if effort:
            kwargs["extra_body"] = {"reasoning_effort": effort}

        # Prefer JSON mode; some endpoints reject it — fall back silently.
        kwargs_json = dict(kwargs, response_format={"type": "json_object"})
        try:
            resp = self._client.chat.completions.create(**kwargs_json)
        except Exception:
            resp = self._client.chat.completions.create(**kwargs)

        text = self._extract_text(resp)
        parsed = parse_json(text)

        if parsed is None:
            # One reformat-retry: echo the raw output and ask for JSON only.
            retry_msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": text or ""},
                {"role": "user", "content":
                    "Return ONLY the JSON object. No prose, no markdown fences."},
            ]
            try:
                resp = self._client.chat.completions.create(
                    model=model, messages=retry_msgs, temperature=0.0,
                    max_tokens=max_tokens)
                parsed = parse_json(self._extract_text(resp))
            except Exception:
                pass

        if parsed is None:
            raise ValueError(f"{role}: model did not return parseable JSON")
        return parsed


class AnthropicProvider:
    """Live hosted-convenience path. Reads ANTHROPIC_API_KEY; tier maps to Claude
    model ids (settings.anthropic_model_fast/strong)."""

    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy import
        self._client = (Anthropic(api_key=settings.anthropic_api_key)
                        if settings.anthropic_api_key else Anthropic())

    def model_for(self, tier: str) -> str:
        return _model_for(tier)

    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict:
        # reasoning_effort is an open-weight knob; accepted for protocol
        # conformance and ignored here (Anthropic uses a different mechanism).
        resp = self._client.messages.create(
            model=self.model_for(tier),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", None) == "text").strip()
        parsed = parse_json(text)
        if parsed is None:
            raise ValueError(f"{role}: model did not return parseable JSON")
        return parsed


class BedrockProvider:
    """DOCUMENTED STUB (not live). Amazon Bedrock with the Nova tier mapping:

        fast   -> settings.bedrock_model_fast    (default amazon.nova-lite-v1:0)
        strong -> settings.bedrock_model_strong  (default amazon.nova-pro-v1:0)

    Constructs without boto3 so provider selection/tier-mapping is testable; any
    actual call raises so it can never be used unimplemented. To make it live:
    add a thin boto3 `bedrock-runtime` `converse` call here mapping tier->model
    via `model_for` and parsing usage from the response — no core changes needed.
    """

    name = "bedrock"

    def model_for(self, tier: str) -> str:
        return _model_for(tier)

    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict:
        raise NotImplementedError(
            "bedrock provider is a documented stub; set PROVIDER=openai_compatible "
            "or PROVIDER=anthropic (Nova mapping: "
            f"fast={settings.bedrock_model_fast}, strong={settings.bedrock_model_strong})")


# Provider id -> class. New providers register here; core selects by PROVIDER.
_PROVIDERS: Dict[str, type] = {
    "openai_compatible": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "bedrock": BedrockProvider,
}


def provider_class(provider_id: str) -> type:
    """The Provider class for an id (no construction; testable without network)."""
    try:
        return _PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(
            f"unknown PROVIDER={provider_id!r}; known: {sorted(_PROVIDERS)}")


def get_provider() -> Provider:
    """Construct the configured provider (PROVIDER, default openai_compatible)."""
    return provider_class(settings.provider)()


# Back-compat aliases.
OpenAICompatLLM = OpenAICompatProvider
AnthropicLLM = AnthropicProvider
get_llm = get_provider
