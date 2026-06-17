"""
Persistence schema (SQLAlchemy).

Three tables:
  participants  - anonymized identity + consent flag. No PII by design.
  learner_state - per-participant concept memory (grasped / shaky) + counters.
                  This is Sol's persistent learner model.
  events        - append-only trace. Every run and every tutor turn lands here
                  with full component telemetry. This IS the §6 data stream
                  (see docs/PRIVACY.md); it is never updated, only inserted.

LearnerState schema v2 (2026-06-03): added `concepts` JSON (canonical per-concept
mastery). Shape: {concept_id: {"state":"shaky"|"grasped", "evidence":int,
"last_seen":iso, "last_review":iso|null, "last_review_ex":str|null}}.
Additive; pre-existing rows default to {}.
MIGRATION: init_db/create_all won't ALTER existing tables. For dev DBs (no real
data yet): recreate. For deployed DBs:
  ALTER TABLE learner_state ADD COLUMN concepts JSON DEFAULT '{}';

Event schema v2 (2026-06-01): added `stance` column (peer|oracle|control|NULL).
Rows written before this change have stance=NULL and are treated as "peer".

Event payload v3 (2026-06-01): the `turn` payload telemetry block gained the
calibrated-uncertainty fields — reasoning_effort, escalated, abstained, and the
confidence_trajectory (planner/reasoner/self_eval). These live inside the JSON
payload (no column change); Step 4's §6 calibration measures key on them.

Event payload v5 (2026-06-02 / F6): the `turn` payload gains an additive optional
field — telemetry.misconception_id (string|null). The reasoner reports the id of
the misconception it judged the student to be exhibiting this turn; null when no
match. This is an exploratory measure, NOT confirmatory. Pre-F6 rows have this
field absent; downstream code must use .get("misconception_id") with a None
default. Control turns carry null by construction (no reasoner runs).

LearnerState schema v3 (goals/reflections): added two ADDITIVE columns — `goals`
JSON (the student's own self-set goals artifact {text, ts, honored}, or null) and
`reflections` JSON (a timestamped list of the student's reflections, each linked
to the goal in force). Opt-in: with no goals/reflections set, both default to
null/[] and behavior is unchanged. No PII; the student's own words only.
MIGRATION (deployed DBs): ALTER TABLE learner_state ADD COLUMN goals JSON;
ALTER TABLE learner_state ADD COLUMN reflections JSON DEFAULT '[]'; (dev: recreate).

LearnerState schema v4 (per-learner customization overlay): added one ADDITIVE
column `overlay` JSON (bounded persona/pedagogy/accommodation knobs, or null).
Opt-in: null overlay leaves behavior unchanged. No PII; enumerated values only.
MIGRATION (deployed DBs): ALTER TABLE learner_state ADD COLUMN overlay JSON; (dev: recreate).

Event types are ADDITIVE: alongside `run` and `turn`, the goals/reflection layer
emits `goal_set`, `goal_alignment_check`, `reflect`, and `reflection_recorded`, and
the customization overlay emits `overlay_set` (new event_type values only; the
8-field row shape and the events.jsonl export contract are unchanged). These only
appear when a student opts in to goals or a customization overlay.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    anon_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LearnerState(Base):
    __tablename__ = "learner_state"

    participant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("participants.id"), primary_key=True
    )
    grasped: Mapped[list] = mapped_column(JSON, default=list)
    shaky: Mapped[list] = mapped_column(JSON, default=list)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    concepts: Mapped[dict] = mapped_column(JSON, default=dict)
    # v3 (opt-in goals/reflections): the student's own self-set goals + reflections.
    goals: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    reflections: Mapped[list] = mapped_column(JSON, default=list)
    # v4 (opt-in per-learner customization overlay): bounded, enumerated knobs
    # (persona/pedagogy/accommodation) that shape HOW the tutor helps. Null = today.
    overlay: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("participants.id"), index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    exercise_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(16))  # study | teach
    event_type: Mapped[str] = mapped_column(String(16))  # run | turn
    stance: Mapped[str | None] = mapped_column(String(16), nullable=True)  # peer | oracle | control
    payload: Mapped[dict] = mapped_column(JSON)  # full telemetry
    note: Mapped[str] = mapped_column(Text, default="")
