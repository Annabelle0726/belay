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

    def limits(self) -> tuple[Limits, ...]:
        return (self.deployment, self.institution, self.classroom, self.learner)
