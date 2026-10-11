# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

LEVELS = ("deployment", "institution", "class", "learner")
UNITS = ("tokens", "microunits", "runs", "wall_ms")


class ControlError(Exception):
    def __init__(self, code: str, status: int = 429, retry_after: int | None = None):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


@dataclass(frozen=True)
class Scope:
    """Construct ONLY from a trusted identity adapter, never request body claims."""

    deployment: str
    institution: str
    classroom: str
    learner: str

    def keys(self) -> tuple[str, ...]:
        parts = (self.deployment, self.institution, self.classroom, self.learner)
        if any(not isinstance(p, str) or not p or len(p) > 128 for p in parts):
            raise ValueError("invalid verified scope")
        return tuple(
            hashlib.sha256(json.dumps(parts[:i]).encode()).hexdigest() for i in range(1, 5)
        )


class Amount(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    tokens: int = Field(default=0, ge=0, le=10**15)
    microunits: int = Field(default=0, ge=0, le=10**15)
    runs: int = Field(default=0, ge=0, le=10**15)
    wall_ms: int = Field(default=0, ge=0, le=10**15)


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    tokens: int | None = Field(default=None, ge=0, le=10**15)
    microunits: int | None = Field(default=None, ge=0, le=10**15)
    runs: int | None = Field(default=None, ge=0, le=10**15)
    wall_ms: int | None = Field(default=None, ge=0, le=10**15)


class Traffic(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    burst: int = Field(default=60, ge=0)
    rate_seconds: int = Field(default=60, ge=1)
    queue_jobs: int = Field(default=100, ge=0)
    queue_bytes: int = Field(default=1048576, ge=0)
    active_jobs: int = Field(default=10, ge=0)
    model_calls: int = Field(default=10, ge=0)
    runner_calls: int = Field(default=4, ge=0)


class ModelQuotas(BaseModel):
    """Optional deployment-wide fixed buckets, independent of scope periods.

    Anchors are explicit UTC epoch seconds supplied by the operator. They do not
    move on restart or policy update. This is not a learner entitlement policy.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    short_period_seconds: int = Field(ge=3600, le=86400, multiple_of=3600)
    short_anchor_utc: int = Field(ge=0, le=10**11)
    short_microunits: int = Field(ge=0, le=10**15)
    week_anchor_utc: int = Field(ge=0, le=10**11)
    week_microunits: int = Field(ge=0, le=10**15)

    def windows(self) -> tuple[tuple[int, int, int], ...]:
        return (
            (self.short_period_seconds, self.short_anchor_utc, self.short_microunits),
            (604800, self.week_anchor_utc, self.week_microunits),
        )


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: str = Field(min_length=1, max_length=64)
    price_version: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    period_seconds: int = Field(default=86400, ge=1, le=31536000)
    deployment: Limits
    institution: Limits
    classroom: Limits
    learner: Limits
    # Per-token prices in currency microunits. Operators must supply a bound
    # covering every configured model; no runtime vendor pricing assumption.
    input_price: int = Field(ge=0, le=10**9)
    output_price: int = Field(ge=0, le=10**9)
    model_quotas: ModelQuotas | None = None
    deployment_traffic: Traffic = Field(default_factory=Traffic)
    institution_traffic: Traffic = Field(default_factory=Traffic)
    classroom_traffic: Traffic = Field(default_factory=Traffic)
    learner_traffic: Traffic = Field(default_factory=Traffic)
    payload_bytes: int = Field(default=65536, ge=1, le=1048576)
    queue_wait_seconds: int = Field(default=120, ge=1, le=3600)
    lease_seconds: int = Field(default=60, ge=1, le=3600)
    execution_seconds: int = Field(default=300, ge=1, le=3600)
    result_seconds: int = Field(default=300, ge=1, le=3600)
    poll_seconds: int = Field(default=2, ge=1, le=60)

    def limits(self) -> tuple[Limits, ...]:
        return (self.deployment, self.institution, self.classroom, self.learner)

    def traffic(self) -> tuple[Traffic, ...]:
        return (
            self.deployment_traffic,
            self.institution_traffic,
            self.classroom_traffic,
            self.learner_traffic,
        )
