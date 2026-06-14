"""Runtime configuration (env-driven, no extra deps)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    # Quantum execution: "local" (offline simulator) or "classiq" (real platform).
    quantum_backend: str = field(default_factory=lambda: _env("QUANTUM_BACKEND", "local"))

    # --- Model layer -------------------------------------------------------
    # Provider: "jetstream" (the JS2 Inference Service, OpenAI-compatible) or
    # "anthropic" (alternate, for off-JS2 development / ceiling comparisons).
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "jetstream"))

    # Resource-aware model tiers, hosted on Jetstream2's inference service.
    # fast  -> Planner + Self-Evaluation (frequent, cheap)
    # strong-> Peer-Reasoner (voice + pedagogy)
    # Both are US-origin, open-weight models served at IU; no commercial key,
    # no per-token cost, and no Jetstream2 SUs are consumed by the service.
    model_tiers: Dict[str, str] = field(default_factory=lambda: {
        "fast": _env("MODEL_FAST", "llama-4-scout"),
        "strong": _env("MODEL_STRONG", "gpt-oss-120b"),
    })

    # Per-tier OpenAI-compatible base URLs. The defaults are the JS2 direct
    # (token-free) endpoints, reachable from any Jetstream2 / IU Research Cloud
    # instance. Off-instance, point both at the Open WebUI proxy
    # (https://llm.jetstream-cloud.org/api) and set LLM_API_KEY to your token.
    tier_base_urls: Dict[str, str] = field(default_factory=lambda: {
        "fast": _env("LLM_BASE_FAST", "https://llm.jetstream-cloud.org/llama-4-scout/v1"),
        "strong": _env("LLM_BASE_STRONG", "https://llm.jetstream-cloud.org/gpt-oss-120b/v1"),
    })

    # gpt-oss exposes configurable reasoning effort (low|medium|high). Applied
    # to the strong tier; omit for the fast tier.
    tier_reasoning: Dict[str, str] = field(default_factory=lambda: {
        "strong": _env("REASONING_STRONG", "high"),
    })

    # Direct (on-instance) access needs no token; the OpenAI SDK still wants a
    # non-empty string, so default to a dummy. Set a real token for the proxy.
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", "EMPTY"))
    llm_temperature: float = field(default_factory=lambda: float(_env("LLM_TEMPERATURE", "0.4")))

    # Evaluation-first loop: how many times the Reasoner may revise after a
    # failing self-evaluation before we gate and ship the best draft.
    max_refine: int = field(default_factory=lambda: int(_env("MAX_REFINE", "1")))

    # Self-verifying worked examples: how many regeneration attempts the
    # orchestrator makes when the reasoner's first worked_example fails
    # verification (does_not_compile | would_solve_current_exercise |
    # prediction_mismatch). 0 = try once, suppress on failure; 1 = one retry.
    max_worked_example_retry: int = field(
        default_factory=lambda: int(_env("MAX_WORKED_EXAMPLE_RETRY", "1"))
    )

    # --- Calibrated uncertainty (Step 3) -----------------------------------
    # Two DISTINCT mechanisms, never conflated:
    #
    # (A) ESCALATION — a CAPABILITY lever applied identically to peer & oracle
    #     (vary stance, hold capability). The Reasoner runs at a default
    #     reasoning effort; if self-evaluation is still under-confident after the
    #     bounded refine, it is re-run at a higher effort and re-evaluated, up to
    #     MAX_ESCALATE times. (Model-swap to a larger open-weight tier is a
    #     future hook if one joins the JS2 menu — see reasoner/llm seam.)
    reasoner_effort_default: str = field(default_factory=lambda: _env("REASONER_EFFORT_DEFAULT", "medium"))
    reasoner_effort_escalated: str = field(default_factory=lambda: _env("REASONER_EFFORT_ESCALATED", "high"))
    tau_escalate: float = field(default_factory=lambda: float(_env("TAU_ESCALATE", "0.55")))
    max_escalate: int = field(default_factory=lambda: int(_env("MAX_ESCALATE", "1")))
    #
    # (B) ABSTENTION — a STANCE behavior, PEER ONLY. If a peer turn is still
    #     below this floor after refine + escalation, the orchestrator overrides
    #     it into a peer-voiced abstention (intervention=escalate, abstained=true).
    #     Oracle never abstains; it returns its best answer.
    tau_abstain: float = field(default_factory=lambda: float(_env("TAU_ABSTAIN", "0.35")))

    # Persistence backend for the store: "sql" (durable) or "memory" (ephemeral).
    store_backend: str = field(default_factory=lambda: _env("STORE_BACKEND", "sql"))

    cors_origins: list = field(default_factory=lambda: _env(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(","))


settings = Settings()
