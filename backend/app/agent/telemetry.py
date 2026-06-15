"""
Per-component usage telemetry (additive §6).

A `UsageMeter` accumulates, per component role (planner / reasoner / self_eval),
the latency, prompt/completion tokens, and cost of each provider call. The
orchestrator activates a meter for the turn (via a ContextVar so the provider
needs no signature change); each `Provider.json` call records into it. The
orchestrator then folds `meter.by_component()` into the trace as an ADDITIVE
`telemetry.component_usage` field.

Tokens come from the provider response (OpenAI-compatible `usage` for
self-hosted; Anthropic `usage` for anthropic) and are None when the provider does
not report them (e.g. a test stub). Cost is provider-configurable and may be 0
for self-hosted.
"""
from __future__ import annotations

import contextvars
from typing import Dict, Optional

_meter: "contextvars.ContextVar[Optional[UsageMeter]]" = contextvars.ContextVar(
    "ptf_usage_meter", default=None)


class UsageMeter:
    def __init__(self) -> None:
        self._by_role: Dict[str, dict] = {}

    def record(self, role: str, *, latency_ms: float,
               prompt_tokens: Optional[int], completion_tokens: Optional[int],
               cost: Optional[float]) -> None:
        e = self._by_role.setdefault(role, {
            "calls": 0, "latency_ms": 0.0,
            "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0,
            "_has_tokens": False, "_has_cost": False,
        })
        e["calls"] += 1
        e["latency_ms"] = round(e["latency_ms"] + latency_ms, 1)
        if prompt_tokens is not None or completion_tokens is not None:
            e["prompt_tokens"] += prompt_tokens or 0
            e["completion_tokens"] += completion_tokens or 0
            e["_has_tokens"] = True
        if cost is not None:
            e["cost"] = round(e["cost"] + cost, 6)
            e["_has_cost"] = True

    def by_component(self) -> Dict[str, dict]:
        """{role: {calls, latency_ms, prompt_tokens, completion_tokens, cost}}.
        Token/cost are None when the provider never reported them."""
        out: Dict[str, dict] = {}
        for role, e in self._by_role.items():
            out[role] = {
                "calls": e["calls"],
                "latency_ms": e["latency_ms"],
                "prompt_tokens": e["prompt_tokens"] if e["_has_tokens"] else None,
                "completion_tokens": e["completion_tokens"] if e["_has_tokens"] else None,
                "cost": e["cost"] if e["_has_cost"] else None,
            }
        return out


def current_meter() -> "Optional[UsageMeter]":
    return _meter.get()


def set_meter(meter: Optional[UsageMeter]):
    """Activate a meter for the current context; returns a token for reset()."""
    return _meter.set(meter)


def reset_meter(token) -> None:
    _meter.reset(token)


def record(role: str, *, latency_ms: float, prompt_tokens: Optional[int],
           completion_tokens: Optional[int], cost: Optional[float]) -> None:
    """Record a provider call into the active meter, if any (no-op otherwise)."""
    meter = _meter.get()
    if meter is not None:
        meter.record(role, latency_ms=latency_ms, prompt_tokens=prompt_tokens,
                     completion_tokens=completion_tokens, cost=cost)
