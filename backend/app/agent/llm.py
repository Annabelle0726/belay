# SPDX-License-Identifier: AGPL-3.0-only
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
import time
from typing import Protocol, runtime_checkable

from ..config import settings
from ..controls.contracts import ControlError
from ..controls.runtime import model_call
from . import telemetry as _tel


def _cost(prompt_tokens, completion_tokens) -> float:
    return round(
        (prompt_tokens or 0) / 1000.0 * settings.cost_per_1k_prompt
        + (completion_tokens or 0) / 1000.0 * settings.cost_per_1k_completion,
        6,
    )


@runtime_checkable
class Provider(Protocol):
    name: str

    def json(
        self,
        *,
        role: str,
        tier: str,
        system: str,
        user: str,
        max_tokens: int = 800,
        reasoning_effort: str | None = None,
    ) -> dict: ...


# Back-compat alias (older imports referenced LLMClient).
LLMClient = Provider


def parse_json(text: str) -> dict | None:
    """Strip fences, then parse. Falls back to the first {...} block. This also
    tolerates reasoning models that prepend analysis before the final JSON."""
    clean = (text or "").strip()
    clean = re.sub(r"^```(?:json)?", "", clean).strip()
    clean = re.sub(r"```$", "", clean).strip()
    try:
        loaded: dict = json.loads(clean)
        return loaded
    except Exception:
        m = re.search(r"\{[\s\S]*\}", clean)
        if m:
            try:
                loaded2: dict = json.loads(m.group(0))
                return loaded2
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

        self._client = OpenAI(
            base_url=settings.openai_base_url, api_key=settings.openai_api_key, max_retries=0
        )

    def _attempt(self, role: str, kwargs: dict):
        started = time.perf_counter()
        ptok = ctok = None
        sent = False

        def send():
            nonlocal sent
            sent = True
            return self._client.chat.completions.create(**kwargs)

        try:
            resp = model_call(
                send,
                json.dumps(kwargs["messages"], ensure_ascii=False),
                kwargs["max_tokens"],
                self._usage,
            )
            ptok, ctok = self._usage(resp)
            return resp
        finally:
            if sent:
                _tel.record(
                    role,
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                    prompt_tokens=ptok,
                    completion_tokens=ctok,
                    cost=_cost(ptok, ctok) if ptok is not None and ctok is not None else None,
                )

    def model_for(self, tier: str) -> str:
        return _model_for(tier)

    @staticmethod
    def _extract_text(resp) -> str:
        msg = resp.choices[0].message
        return getattr(msg, "content", None) or getattr(msg, "reasoning_content", "") or ""

    @staticmethod
    def _usage(resp):
        u = getattr(resp, "usage", None)
        if u is None:
            return None, None
        return getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None)

    def json(
        self,
        *,
        role: str,
        tier: str,
        system: str,
        user: str,
        max_tokens: int = 800,
        reasoning_effort: str | None = None,
    ) -> dict:
        model = self.model_for(tier)
        kwargs: dict = dict(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=settings.llm_temperature,
            max_tokens=max_tokens,
        )
        # "Thinking" is a model CAPABILITY, not sent unconditionally. Default OFF
        # for openai_compatible so ordinary non-reasoning local models
        # (llama3.2/mistral/qwen2.5) work — they reject an unknown reasoning param.
        # Opt in with OPENAI_REASONING=1 for an endpoint serving a reasoning model;
        # the effort then comes from the per-call escalation lever or the strong-
        # tier default. No governance logic is involved either way.
        if settings.openai_reasoning:
            effort = reasoning_effort or (settings.reasoning_strong if tier == "strong" else "")
            if effort:
                kwargs["extra_body"] = {"reasoning_effort": effort}

        # Retry only an explicit request-format rejection. A timeout/lost
        # response is uncertain spending, never a trigger for a blind retry.
        kwargs_json = dict(kwargs, response_format={"type": "json_object"})
        try:
            resp = self._attempt(role, kwargs_json)
        except ControlError:
            raise
        except Exception as exc:
            if getattr(exc, "status_code", None) not in {400, 422}:
                raise
            resp = self._attempt(role, kwargs)

        text = self._extract_text(resp)
        parsed = parse_json(text)

        if parsed is None:
            # One reformat-retry: echo the raw output and ask for JSON only.
            retry_msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": text or ""},
                {
                    "role": "user",
                    "content": "Return ONLY the JSON object. No prose, no markdown fences.",
                },
            ]
            try:
                resp = self._attempt(
                    role,
                    dict(
                        model=model,
                        messages=retry_msgs,
                        temperature=0.0,
                        max_tokens=max_tokens,
                    ),
                )
                parsed = parse_json(self._extract_text(resp))
            except ControlError:
                raise
            except Exception:
                raise

        if parsed is None:
            raise ValueError(f"{role}: model did not return parseable JSON")

        return parsed


class AnthropicProvider:
    """Live hosted-convenience path. Reads ANTHROPIC_API_KEY; tier maps to Claude
    model ids (settings.anthropic_model_fast/strong)."""

    name = "anthropic"

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy import

        self._client = (
            Anthropic(api_key=settings.anthropic_api_key, max_retries=0)
            if settings.anthropic_api_key
            else Anthropic(max_retries=0)
        )

    def model_for(self, tier: str) -> str:
        return _model_for(tier)

    def json(
        self,
        *,
        role: str,
        tier: str,
        system: str,
        user: str,
        max_tokens: int = 800,
        reasoning_effort: str | None = None,
    ) -> dict:
        # reasoning_effort is the open-weight knob; Anthropic uses extended
        # thinking instead. Thinking is this provider's CAPABILITY (default on);
        # openai_compatible defaults it off. No governance logic is involved.
        t0 = time.perf_counter()
        kwargs: dict = dict(
            model=self.model_for(tier),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if settings.anthropic_thinking:
            budget = max(settings.anthropic_thinking_budget, 1024)  # Anthropic minimum
            # max_tokens must exceed the thinking budget; extended thinking also
            # requires the default temperature (so we omit temperature here).
            kwargs["max_tokens"] = max(max_tokens, budget + 512)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}

        def usage(resp):
            value = getattr(resp, "usage", None)
            if value is None:
                return None, None
            prompt = getattr(value, "input_tokens", None)
            # Cache tokens are separately reported by Anthropic. Charge them
            # conservatively at the configured maximum input price.
            if prompt is not None:
                prompt += (getattr(value, "cache_creation_input_tokens", 0) or 0) + (
                    getattr(value, "cache_read_input_tokens", 0) or 0
                )
            return prompt, getattr(value, "output_tokens", None)

        ptok = ctok = None
        sent = False

        def send():
            nonlocal sent
            sent = True
            return self._client.messages.create(**kwargs)

        try:
            resp = model_call(
                send,
                system + user,
                kwargs["max_tokens"],
                usage,
            )
            ptok, ctok = usage(resp)
        finally:
            if sent:
                _tel.record(
                    role,
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                    prompt_tokens=ptok,
                    completion_tokens=ctok,
                    cost=_cost(ptok, ctok) if ptok is not None and ctok is not None else None,
                )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
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

    def json(
        self,
        *,
        role: str,
        tier: str,
        system: str,
        user: str,
        max_tokens: int = 800,
        reasoning_effort: str | None = None,
    ) -> dict:
        raise NotImplementedError(
            "bedrock provider is a documented stub; set PROVIDER=openai_compatible "
            "or PROVIDER=anthropic (Nova mapping: "
            f"fast={settings.bedrock_model_fast}, strong={settings.bedrock_model_strong})"
        )


# Provider id -> class. New providers register here; core selects by PROVIDER.
_PROVIDERS: dict[str, type] = {
    "openai_compatible": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "bedrock": BedrockProvider,
}


def provider_class(provider_id: str) -> type:
    """The Provider class for an id (no construction; testable without network)."""
    try:
        return _PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(f"unknown PROVIDER={provider_id!r}; known: {sorted(_PROVIDERS)}") from None


def get_provider() -> Provider:
    """Construct the configured provider (PROVIDER, default openai_compatible)."""
    inst: Provider = provider_class(settings.provider)()
    return inst


# Back-compat aliases.
OpenAICompatLLM = OpenAICompatProvider
AnthropicLLM = AnthropicProvider
get_llm = get_provider
