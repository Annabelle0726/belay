# SPDX-License-Identifier: AGPL-3.0-only
"""Pydantic schemas for the HTTP edge. Internals use plain dicts; validation
lives here at the boundary."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class RecentTurn(BaseModel):
    """One turn of the client's `recent` history window (the canonical wire shape).

    Built through `coerce_recent_turns`, which also accepts the legacy spelling, so
    the strict field patterns here are the *post-normalization* contract.
    """

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = ""


#: Raw-history spelling -> canonical wire role. The agent layer reads the history to
#: decide whether the STUDENT asked for the answer or signalled distress (the safety
#: floors), so this map is deliberately explicit: anything not listed is dropped rather
#: than guessed, and can never masquerade as student speech.
_ROLE_ALIASES = {
    "user": "user",
    "student": "user",
    "learner": "user",
    "assistant": "assistant",
    "sol": "assistant",
    "tutor": "assistant",
    "system": "assistant",
}


def coerce_recent_turns(raw: object) -> list[RecentTurn]:
    """Normalize a client's `recent` history window onto `RecentTurn`.

    Canonical wire shape is ``{"role": "user"|"assistant", "content": "..."}``. The
    legacy ``{"who": "student"|"tutor", "text": "..."}`` spelling — still sent by the
    embeddable widget, which may be cached in a host page — normalizes onto the same
    model, so both clients validate.

    A malformed entry (not an object, no role, or an unknown role) is DROPPED rather
    than coerced or rejected: coercing a mislabelled turn could let it masquerade as
    student speech at the floor checks, while a 422 would cost the learner their
    reply over one junk history line.
    """
    if not isinstance(raw, list):
        return []
    turns: list[RecentTurn] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_role = item.get("role", item.get("who"))
        raw_text = item.get("content", item.get("text", ""))
        role = _ROLE_ALIASES.get(str(raw_role).strip().lower()) if raw_role is not None else None
        if role is None:
            continue
        turns.append(RecentTurn(role=role, content="" if raw_text is None else str(raw_text)))
    return turns


class DialogueTurn(BaseModel):
    """An *internal* dialogue turn: ``who`` is ``"student"`` or the active pack's
    persona id.

    This is the shape the agent layer reads as ``recent_dialogue`` — `RecentTurn` is
    what crosses the HTTP edge, and ``main.sol_turn`` translates between the two.
    """

    who: str
    text: str


class RunRequest(BaseModel):
    participant_id: str
    exercise_id: str
    source: str


class RunResult(BaseModel):
    """Pack-agnostic run-result envelope (§6 schema v6).

    Top level is domain-independent so the §6 trace schema is stable across
    packs; ``metric`` is the pack's primary scalar (e.g. the DS held-out
    score / loss) and all other domain-specific data (e.g. checks /
    stdout) lives in the namespaced ``pack`` envelope.
    """

    model_config = {"extra": "allow"}

    ok: bool
    goalMet: bool | None = None
    metric: float | None = None
    error: str | None = None
    pack: dict | None = None  # {"id": <pack id>, ...domain-specific fields}


class SolTurnRequest(BaseModel):
    participant_id: str
    exercise_id: str
    event: str = Field("chat", pattern="^(run|chat)$")
    mode: str = Field("study", pattern="^(study|teach)$")
    stance: str = Field("peer", pattern="^(peer|oracle|control)$")
    source: str = ""
    # The run envelope as the client echoes it back (RunResult shape). Accepts Any so a
    # client that wraps or extends the envelope still validates; a non-mapping value is
    # dropped by the validator below rather than crashing the turn in `context.py`.
    result: Any | None = None
    recent: list[RecentTurn] = Field(default_factory=list)
    signals: dict | None = None
    request: str | None = None  # e.g. "reflect" — student-initiated reflect
    overlay: dict | None = None  # opt-in per-learner customization overlay (bounded)

    @field_validator("recent", mode="before")
    @classmethod
    def _normalize_recent(cls, v: object) -> list[RecentTurn]:
        """Accept both history spellings and drop unlabelable entries: one junk
        history line must not cost the learner their reply (see
        `coerce_recent_turns`)."""
        return coerce_recent_turns(v)

    @field_validator("result", mode="before")
    @classmethod
    def _result_must_be_a_mapping(cls, v: object) -> object:
        """`context._last_result` calls ``.get`` on this, so anything that is not a
        mapping (a list, a string, a number) would 500 the turn. Drop it to ``None``
        — the tutor then reads "no run yet", which is the honest degradation."""
        if v is None or isinstance(v, dict):
            return v
        return None


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
    worked_example: dict | None = None  # telemetry only; UI may ignore
    components: dict[str, Any] = {}


class GoalRequest(BaseModel):
    participant_id: str
    text: str = ""  # the student's own words; empty clears the goals


class ReflectionRequest(BaseModel):
    participant_id: str
    text: str  # the student's reflection, in their own words


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
