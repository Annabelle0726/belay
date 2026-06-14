"""Pydantic schemas for the HTTP edge. Internals use plain dicts; validation
lives here at the boundary."""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DialogueTurn(BaseModel):
    who: str  # "student" | "sol"
    text: str


class RunRequest(BaseModel):
    participant_id: str
    exercise_id: str
    source: str


class DistPoint(BaseModel):
    bits: str
    p: float


class RunResult(BaseModel):
    ok: bool
    backend: Optional[str] = None
    n: Optional[int] = None
    gates: Optional[List[dict]] = None
    dist: Optional[List[DistPoint]] = None
    goalMet: Optional[bool] = None
    diff: Optional[str] = None
    tvd: Optional[float] = None
    error: Optional[str] = None


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


class ParticipantRequest(BaseModel):
    anon_code: str
    consent: bool = False


class ParticipantResponse(BaseModel):
    id: str
    anon_code: str
    consent: bool
