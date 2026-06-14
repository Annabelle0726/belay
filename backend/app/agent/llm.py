"""
LLM access + resource-aware model tiering.

The AWS draft's "resource-aware orchestration" is realized here as concrete
model tiers served by the **Jetstream2 Inference Service** (OpenAI-compatible,
US-origin open-weight models, hosted at IU): the Planner and Self-Evaluator run
on a fast tier (Llama 4 Scout), the Peer-Reasoner on a stronger reasoning tier
(gpt-oss-120b, high effort). A backend running on a Jetstream2 instance reaches
these endpoints with no token and at no SU cost.

`LLMClient` is a Protocol with a single `json(...)` method, so tests inject a
deterministic stub and exercise the whole evaluation-first loop with no network.
`get_llm()` returns the configured provider.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Protocol

from ..config import settings


class LLMClient(Protocol):
    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict: ...


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


class OpenAICompatLLM:
    """Client for any OpenAI-compatible endpoint; defaults to the Jetstream2
    Inference Service. Each tier may have its own base URL (the JS2 direct
    endpoints are per-model), so we keep one OpenAI client per base URL."""

    def __init__(self) -> None:
        from openai import OpenAI  # lazy import
        self._OpenAI = OpenAI
        self._clients: Dict[str, object] = {}
        self._tiers = settings.model_tiers
        self._bases = settings.tier_base_urls
        self._reasoning = settings.tier_reasoning

    def _client_for(self, base_url: str):
        if base_url not in self._clients:
            self._clients[base_url] = self._OpenAI(base_url=base_url, api_key=settings.llm_api_key)
        return self._clients[base_url]

    @staticmethod
    def _extract_text(resp) -> str:
        msg = resp.choices[0].message
        return (getattr(msg, "content", None)
                or getattr(msg, "reasoning_content", "")
                or "")

    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict:
        base  = self._bases.get(tier, self._bases["fast"])
        model = self._tiers.get(tier, self._tiers["fast"])
        client = self._client_for(base)

        # Base request kwargs.
        kwargs: dict = dict(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=settings.llm_temperature,
            max_tokens=max_tokens,
        )
        # A per-call reasoning_effort (the escalation lever) overrides the tier
        # default. Model-swap to a larger open-weight tier would slot in right
        # here (pick `model`/`base` by effort) — a clean future seam, not built.
        effort = reasoning_effort or self._reasoning.get(tier)
        if effort:
            kwargs["extra_body"] = {"reasoning_effort": effort}

        # Prefer JSON mode so open-weight models return clean JSON without fences.
        # Some endpoints reject the parameter; fall back silently if they do.
        kwargs_json = dict(kwargs, response_format={"type": "json_object"})
        try:
            resp = client.chat.completions.create(**kwargs_json)
        except Exception:
            resp = client.chat.completions.create(**kwargs)

        text = self._extract_text(resp)
        parsed = parse_json(text)

        if parsed is None:
            # One reformat-retry: echo the raw output back and ask for JSON only.
            # Temperature 0 for determinism; no response_format (already failed once).
            retry_msgs = [
                {"role": "system",    "content": system},
                {"role": "user",      "content": user},
                {"role": "assistant", "content": text or ""},
                {"role": "user",      "content":
                    "Return ONLY the JSON object. No prose, no markdown fences."},
            ]
            try:
                resp2 = client.chat.completions.create(
                    model=model, messages=retry_msgs,
                    temperature=0.0, max_tokens=max_tokens,
                )
                parsed = parse_json(self._extract_text(resp2))
            except Exception:
                pass

        if parsed is None:
            raise ValueError(f"{role}: model did not return parseable JSON")
        return parsed


class AnthropicLLM:
    """Alternate provider (off-JS2 development / ceiling comparisons). Reads
    ANTHROPIC_API_KEY; expects model_tiers set to Claude model strings."""

    def __init__(self) -> None:
        from anthropic import Anthropic  # lazy import
        self._client = Anthropic()
        self._tiers: Dict[str, str] = settings.model_tiers

    def json(self, *, role: str, tier: str, system: str, user: str,
             max_tokens: int = 800, reasoning_effort: str | None = None) -> dict:
        # reasoning_effort is a JS2/open-weight knob; accepted for protocol
        # conformance and ignored here (Anthropic uses a different mechanism).
        model = self._tiers.get(tier, self._tiers["fast"])
        resp = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        parsed = parse_json(text)
        if parsed is None:
            raise ValueError(f"{role}: model did not return parseable JSON")
        return parsed


def get_llm() -> LLMClient:
    """Return the configured LLM client (default: Jetstream2 inference)."""
    if settings.llm_provider == "anthropic":
        return AnthropicLLM()
    return OpenAICompatLLM()
