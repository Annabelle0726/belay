# SPDX-License-Identifier: AGPL-3.0-only
"""Request schemas for the Quad sidecar. PII is rejected by `pii.assert_no_pii`
on the RAW body before these parse, so the models stay permissive."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...core.domain.dialogue import Turn
from ...core.domain.dialogue import coerce_recent_turns as _coerce_recent_turns


class QuadDialogueTurn(BaseModel):
    """One turn of the client's `recent` window, same contract as `/api/sol/turn`.

    Accepts ``{role, content}`` and the legacy ``{who, text}``; a turn that cannot be
    labelled is dropped by `coerce_recent_turns` rather than guessed, because the
    agent layer reads the student's latest turn for its reflect / distress /
    answer-seeking checks (see `app.core.domain.dialogue`).
    """

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = ""

    def as_turn(self) -> Turn:
        return Turn(role=self.role, content=self.content)


def coerce_quad_recent(raw: object) -> list[QuadDialogueTurn]:
    return [QuadDialogueTurn(role=t.role, content=t.content) for t in _coerce_recent_turns(raw)]


class QuadTurnRequest(BaseModel):
    # extra="allow" so any stray (potentially PII) field is captured rather than
    # silently dropped; the raw body is PII-checked before this parses.
    model_config = ConfigDict(extra="allow")

    pseudo_id: str  # pseudonymous host id, e.g. "gh:12345"
    exercise_id: str
    source: str = ""
    event: str = "chat"
    mode: str = "study"
    stance: str = "peer"
    recent: list[QuadDialogueTurn] = Field(default_factory=list)
    signals: dict | None = None

    @field_validator("recent", mode="before")
    @classmethod
    def _normalize_recent(cls, v: object) -> list[QuadDialogueTurn]:
        return coerce_quad_recent(v)

    # OPTIONAL per-learner customization overlay (bounded knobs). Input, never
    # authority: floor-checked + normalized like goals; cannot loosen the leak or
    # wellbeing floor. Carried on the turn and persisted where goals ride.
    overlay: dict | None = None
    # READ-ONLY context. A Quad gradingspec run result maps onto the pack's run
    # result (the §1 gradingspec convergence). There is NO write path back.
    gradingspec_result: dict | None = None
    consent: bool = False  # DMP §3 event-trace gating; default ephemeral
