"""Pydantic schemas for the HTTP edge. Internals use plain dicts; validation
lives here at the boundary."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DialogueTurn(BaseModel):
    who: str  # "student" | the active pack's persona id (e.g. "sol"), supplied through the seam
    text: str


class RunRequest(BaseModel):
    participant_id: str
    exercise_id: str
    source: str


class RunResult(BaseModel):
    """Pack-agnostic run-result envelope (§6 schema v6).

    Top level is domain-independent so the §6 trace schema is stable across
    packs; ``metric`` is the pack's primary scalar (quantum tvd; DS held-out
    score / loss) and all other domain-specific data (gates / dist / diff /
    checks / stdout) lives in the namespaced ``pack`` envelope.
    """
    model_config = {"extra": "allow"}

    ok: bool
    goalMet: bool | None = None
    metric: float | None = None
    error: str | None = None
    pack: dict | None = None   # {"id": <pack id>, ...domain-specific fields}


class SolTurnRequest(BaseModel):
    participant_id: str
    exercise_id: str
    event: str = Field("chat", pattern="^(run|chat)$")
    mode: str = Field("study", pattern="^(study|teach)$")
    stance: str = Field("peer", pattern="^(peer|oracle|control)$")
    source: str = ""
    result: dict | None = None
    recent: list[DialogueTurn] = []
    signals: dict | None = None
    request: str | None = None   # e.g. "reflect" — student-initiated reflect
    overlay: dict | None = None  # opt-in per-learner customization overlay (bounded)


class Memory(BaseModel):
    grasped: list[str] = []
    shaky: list[str] = []


class SolTurnResponse(BaseModel):
    affective_state: str
    affect_reasoning: str
    confidence: float
    intervention: str
    planner_note: str
    self_critique: str
    governance: str
    memory: Memory
    message: str
    check_question: str | None = None
    worked_example: dict | None = None   # telemetry only; UI may ignore
    components: dict[str, Any] = {}


class GoalRequest(BaseModel):
    participant_id: str
    text: str = ""          # the student's own words; empty clears the goals


class ReflectionRequest(BaseModel):
    participant_id: str
    text: str               # the student's reflection, in their own words


class OverlayRequest(BaseModel):
    participant_id: str
    # bounded knobs (persona/pedagogy/accommodation); null/empty clears. Floor-checked
    # and normalized server-side; input only, never authority over a floor.
    overlay: dict | None = None


class ParticipantRequest(BaseModel):
    anon_code: str
    consent: bool = False


class ParticipantResponse(BaseModel):
    id: str
    anon_code: str
    consent: bool
