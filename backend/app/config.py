"""Runtime configuration (env-driven, no extra deps)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


@dataclass
class Settings:
    # --- Model/inference provider seam -------------------------------------
    # PROVIDER selects the inference provider (and is recorded in the §6 telemetry
    # `provider` field). The fast/strong TIER POLICY (which component uses which
    # tier) lives in core and is provider-agnostic; only the tier->concrete-model
    # mapping is per-provider config below.
    #   openai_compatible (default, self-hosted first-class): any OpenAI-compatible
    #     endpoint (Ollama, vLLM, a Jetstream2-hosted model, MESA AI-Verde) via
    #     base_url + model(s) + optional key. Works with NO Anthropic dependency,
    #     enabling a zero-external-API deployment.
    #   anthropic (hosted convenience): wraps the Anthropic client; needs the
    #     anthropic package + ANTHROPIC_API_KEY.
    #   bedrock (documented stub; not live): Amazon Nova tier mapping below.
    provider: str = field(default_factory=lambda: _env("PROVIDER", "openai_compatible"))

    # openai_compatible — single base_url serves all tiers (Ollama/vLLM/etc).
    openai_base_url: str = field(default_factory=lambda: _env(
        "OPENAI_BASE_URL", "http://localhost:11434/v1"))   # Ollama default
    # Token-free local endpoints still want a non-empty string for the SDK.
    openai_api_key: str = field(default_factory=lambda: _env(
        "OPENAI_API_KEY", _env("LLM_API_KEY", "EMPTY")))
    openai_model_fast: str = field(default_factory=lambda: _env("MODEL_FAST", "llama3.2"))
    openai_model_strong: str = field(default_factory=lambda: _env("MODEL_STRONG", "llama3.2"))
    # Optional reasoning-effort knob (gpt-oss etc.); empty = not sent. Applied to
    # the strong tier only.
    reasoning_strong: str = field(default_factory=lambda: _env("REASONING_STRONG", ""))

    # anthropic
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY", ""))
    anthropic_model_fast: str = field(default_factory=lambda: _env(
        "ANTHROPIC_MODEL_FAST", "claude-haiku-4-5-20251001"))
    anthropic_model_strong: str = field(default_factory=lambda: _env(
        "ANTHROPIC_MODEL_STRONG", "claude-sonnet-4-6"))

    # bedrock (stub) — Amazon Nova fast/strong mapping, written down for the
    # documented stub; not live.
    bedrock_model_fast: str = field(default_factory=lambda: _env(
        "BEDROCK_MODEL_FAST", "amazon.nova-lite-v1:0"))
    bedrock_model_strong: str = field(default_factory=lambda: _env(
        "BEDROCK_MODEL_STRONG", "amazon.nova-pro-v1:0"))

    llm_temperature: float = field(default_factory=lambda: float(_env("LLM_TEMPERATURE", "0.4")))

    # Cost telemetry (Workstream C): provider-configurable USD per 1k tokens.
    # Default 0 — self-hosted inference is free; set for a metered hosted provider.
    cost_per_1k_prompt: float = field(default_factory=lambda: float(_env("COST_PER_1K_PROMPT", "0")))
    cost_per_1k_completion: float = field(default_factory=lambda: float(_env("COST_PER_1K_COMPLETION", "0")))

    @property
    def model_tiers(self) -> Dict[str, str]:
        """Active provider's tier->concrete-model mapping ({fast, strong}). For a
        single-model self-hosted endpoint, fast and strong map to the same model."""
        if self.provider == "anthropic":
            return {"fast": self.anthropic_model_fast, "strong": self.anthropic_model_strong}
        if self.provider == "bedrock":
            return {"fast": self.bedrock_model_fast, "strong": self.bedrock_model_strong}
        return {"fast": self.openai_model_fast, "strong": self.openai_model_strong}

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

    # --- Durable store DSN -------------------------------------------------
    # SQLite is the zero-config durable DEFAULT (a local file; no server). Postgres
    # is OPT-IN behind the same store interface — set DATABASE_URL to a Postgres DSN
    # (e.g. postgresql+psycopg://user:pass@host:5432/db). No code path requires
    # Postgres; it is for scale, not a prerequisite (Quad §7 / SQLite-first).
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./qimvp.db"))

    @property
    def store_is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    cors_origins: list = field(default_factory=lambda: _env(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(","))


settings = Settings()
