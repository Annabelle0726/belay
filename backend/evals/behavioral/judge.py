# SPDX-License-Identifier: AGPL-3.0-only
"""
The benchmark judge — a SEPARATE, strong model that scores the genuinely
qualitative rubrics (grounded, concrete, question). Configured through the same
provider concept as the tutor (JUDGE_PROVIDER / JUDGE_MODEL) but constructed
independently so it is distinct from the model under test, and run at
temperature 0.

CREDIBILITY: a model cannot grade its own output. The runner sets `credible`
False when the judge model equals the tutor model under test; the report then
marks the judge-scored families self-judged and not credible.

no_solution is NOT judged here — it is a deterministic gate verdict (see
families.no_solution). The judge only scores the qualitative signals.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.llm import parse_json

_RUBRICS = {
    "grounded": (
        "You grade a peer tutor's single message. Score how GROUNDED it is in the "
        "student's actual code / result / situation (not generic advice), 1-5. "
        'Respond with ONLY JSON: {"score": <1-5>, "note": "one clause"}.'
    ),
    "concrete": (
        "You grade a peer tutor's encourage message to a frustrated/disengaged "
        "student. Score how CONCRETE it is — does it give ONE clear next step (not "
        'vague "keep trying")? 1-5. Respond with ONLY JSON: {"score": <1-5>, "note": "one clause"}.'
    ),
    "question": (
        "You grade a peer tutor's revisit message. Score whether it poses EXACTLY "
        "ONE clear retrieval/prediction question (5 = exactly one question; 1 = no "
        'question or several). Respond with ONLY JSON: {"score": <1-5>, "note": "one clause"}.'
    ),
}


class Judge:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
        credible: bool = True,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.credible = credible
        self._kind = "anthropic" if provider == "anthropic" else "openai"
        # Dynamically one of two SDK clients (Anthropic | OpenAI), selected at runtime
        # and accessed via different attributes per branch in `_complete`. `Any` is the
        # honest type for a dual-provider client (avoids per-line ignores on each use).
        self._client: Any
        if self._kind == "anthropic":
            from anthropic import Anthropic

            self._client = Anthropic(api_key=api_key) if api_key else Anthropic()
        else:
            from openai import OpenAI

            self._client = OpenAI(base_url=base_url, api_key=api_key or "EMPTY")

    def _complete(self, system: str, user: str) -> str:
        if self._kind == "anthropic":
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=200,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=200,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    def score(self, rubric: str, situation: dict, message: str) -> int:
        system = _RUBRICS[rubric]
        user = json.dumps({"situation": situation, "tutor_message": message})
        parsed = parse_json(self._complete(system, user)) or {}
        val = parsed.get("score", parsed.get(rubric))
        try:
            return max(1, min(5, int(round(float(val)))))
        except (TypeError, ValueError):
            return 1
