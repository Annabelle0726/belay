# SPDX-License-Identifier: AGPL-3.0-only
"""Independent intake, page, retention and model context bounds."""

from __future__ import annotations

import json

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from ..agent.llm import Provider
from ..config import settings
from .policy import Policy


def wire_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def recent_window(history: list[dict], message: str, persona: str, policy: Policy) -> list[dict]:
    def convert(m):
        return {"who": "student" if m["role"] == "student" else persona, "text": m["text"]}

    recent = [{"who": "student", "text": message}]
    budget = policy.context_tokens - policy.response_tokens
    if wire_size(recent) > budget:
        raise HTTPException(413, "new message exceeds context allowance")
    # Completed exchanges only, retaining whole pairs in their original order.
    for i in range(len(history) - 2, -1, -2):
        pair = [convert(m) for m in history[i : i + 2]]
        if wire_size(pair + recent) > budget:
            break
        recent = pair + recent
    return recent


class BoundedProvider:
    def __init__(self, provider: Provider, policy: Policy):
        self.provider = provider
        self.policy = policy
        self.name = provider.name

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
        # Conservative UTF-8 byte accounting, plus a fixed framing allowance.
        # No generated summaries and no tokenizer/model service is needed.
        p = self.policy
        if len(system.encode()) + len(user.encode()) + 256 + p.response_tokens > p.model_tokens:
            raise HTTPException(413, "model input exceeds context allowance")
        if self.name == "anthropic" and settings.anthropic_thinking:
            # That adapter may silently increase max_tokens beyond this reservation.
            raise HTTPException(503, "bounded dialogue requires extended thinking disabled")
        result: dict = self.provider.json(
            role=role,
            tier=tier,
            system=system,
            user=user,
            max_tokens=min(max_tokens, p.response_tokens),
            reasoning_effort=reasoning_effort,
        )
        return result


def bounded_route(policy_factory):
    class BoundedRoute(APIRoute):
        def get_route_handler(self):
            original = super().get_route_handler()

            async def handle(request: Request):
                # This runs before FastAPI JSON/Pydantic parsing and dependencies.
                # Accumulate at most the configured cap, including chunked bodies.
                cap = policy_factory().max_body_bytes
                if cap <= 0:
                    raise HTTPException(503, "invalid dialogue intake limit")
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > cap:
                        raise HTTPException(413, "request body limit exceeded")
                    chunks.append(chunk)
                request._body = b"".join(chunks)
                return await original(request)

            return handle

    return BoundedRoute
