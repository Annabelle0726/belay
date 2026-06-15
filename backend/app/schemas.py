"""Pydantic schemas for the HTTP edge. Internals use plain dicts; validation
lives here at the boundary."""
from __future__ import annotations

from typing import Any, List, Optional

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
    goalMet: Optional[bool] = None
    metric: Optional[float] = None
    error: Optional[str] = None
    pack: Optional[dict] = None   # {"id": <pack id>, ...domain-specific fields}


class SolTurnRequest(BaseModel):
    participant_id: str
    exercise_id: str
    event: str = Field("chat", pattern="^(run|chat)$")
    mode: str = Field("study", pattern="^(study|teach)$")
    stance: str = Field("peer", pattern="^(peer|oracle|control)$")
    source: str = ""
    result: Optional[dict] = None
    recent: List[DialogueTurn] = []
    signals: Optional[dict] = None


class Memory(BaseModel):
    grasped: List[str] = []
    shaky: List[str] = []


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
    check_question: Optional[str] = None
    worked_example: Optional[dict] = None   # telemetry only; UI may ignore
    components: dict[str, Any] = {}


class GoalRequest(BaseModel):
    participant_id: str
    text: str = ""          # the student's own words; empty clears the goals


class ReflectionRequest(BaseModel):
    participant_id: str
    text: str               # the student's reflection, in their own words


class ParticipantRequest(BaseModel):
    anon_code: str
    consent: bool = False


class ParticipantResponse(BaseModel):
    id: str
    anon_code: str
    consent: bool
