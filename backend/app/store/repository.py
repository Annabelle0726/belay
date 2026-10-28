# SPDX-License-Identifier: AGPL-3.0-only
"""
Store layer.

`Store` is the interface the agent depends on (load/save learner state, append
trace events). Two implementations:

    InMemoryStore - zero dependencies; used in tests and quick local runs.
    SqlStore      - SQLAlchemy-backed; the durable store for a pilot.

Keeping the agent behind this protocol means the evaluation-first loop is fully
testable with no database and no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol


def make_event(
    participant_id: str,
    exercise_id: str,
    mode: str,
    event_type: str,
    payload: dict,
    note: str = "",
    stance: str | None = None,
) -> dict:
    """Canonical trace-event record (the stable eight-field §6 row shape; schema v6).

    The row shape is fixed; event_type values are ADDITIVE and adding a new one does
    not change the row shape or the events.jsonl export contract.
    """
    return {
        "participant_id": participant_id,
        "ts": datetime.now(UTC).isoformat(),
        "exercise_id": exercise_id,
        "mode": mode,
        # run | turn | goal_set | goal_alignment_check | reflect | reflection_recorded
        #     | overlay_set | retrieval | distress
        "event_type": event_type,
        "stance": stance,  # peer | oracle | control | None (run events)
        "payload": payload,
        "note": note,
    }


def merge_memory(prev: dict, update: dict) -> dict:
    """Merge a turn's grasped/shaky into the running learner model.
    A concept that becomes grasped is removed from shaky; order preserved."""
    grasped = list(dict.fromkeys([*prev.get("grasped", []), *update.get("grasped", [])]))
    shaky = [
        c
        for c in dict.fromkeys([*prev.get("shaky", []), *update.get("shaky", [])])
        if c not in grasped
    ]
    return {"grasped": grasped, "shaky": shaky}


class Store(Protocol):
    def get_learner_state(self, participant_id: str) -> dict: ...
    def save_learner_state(self, participant_id: str, state: dict) -> None: ...
    def append_event(self, event: dict) -> None: ...
    def attempts(self, participant_id: str, exercise_id: str) -> int: ...
    def export_jsonl(self, participant_id: str | None = None) -> str: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._state: dict[str, dict] = {}
        self._course_counts: dict[tuple[str, str], int] = {}
        self._course_lock = Lock()
        self._events: list[dict] = []

    def get_learner_state(self, participant_id: str) -> dict:
        return self._state.get(
            participant_id,
            {
                "grasped": [],
                "shaky": [],
                "attempts": 0,
                "concepts": {},
                "goals": None,
                "reflections": [],
                "overlay": None,
            },
        )

    def save_learner_state(self, participant_id: str, state: dict) -> None:
        self._state[participant_id] = state

    def append_event(self, event: dict) -> None:
        self._events.append(event)

    def attempts(self, participant_id: str, exercise_id: str) -> int:
        return sum(
            1
            for e in self._events
            if e["participant_id"] == participant_id
            and e["exercise_id"] == exercise_id
            and e["event_type"] == "run"
        )

    def record_course_attempt(self, participant_id: str, exercise_id: str) -> None:
        with self._course_lock:
            key = (participant_id, exercise_id)
            self._course_counts[key] = self._course_counts.get(key, 0) + 1

    def course_attempts(self, participant_id: str, exercise_id: str) -> int:
        return self._course_counts.get((participant_id, exercise_id), 0)

    def export_jsonl(self, participant_id: str | None = None) -> str:
        rows = [e for e in self._events if participant_id in (None, e["participant_id"])]
        return "\n".join(json.dumps(r) for r in rows)


class SqlStore:
    """SQLAlchemy-backed store. Lazily imports models/db so InMemoryStore stays
    usable without SQLAlchemy installed."""

    def __init__(self) -> None:
        from .db import SessionLocal, init_db

        init_db()
        self._Session = SessionLocal

    def get_learner_state(self, participant_id: str) -> dict:
        from .models import LearnerState

        with self._Session() as s:
            row = s.get(LearnerState, participant_id)
            if not row:
                return {
                    "grasped": [],
                    "shaky": [],
                    "attempts": 0,
                    "concepts": {},
                    "goals": None,
                    "reflections": [],
                    "overlay": None,
                }
            return {
                "grasped": row.grasped or [],
                "shaky": row.shaky or [],
                "attempts": row.attempts,
                "concepts": row.concepts or {},
                "goals": row.goals,
                "reflections": row.reflections or [],
                "overlay": row.overlay,
            }

    def save_learner_state(self, participant_id: str, state: dict) -> None:
        from .models import LearnerState

        with self._Session() as s:
            row = s.get(LearnerState, participant_id)
            if not row:
                row = LearnerState(participant_id=participant_id)
                s.add(row)
            row.grasped = state.get("grasped", [])
            row.shaky = state.get("shaky", [])
            row.attempts = state.get("attempts", row.attempts or 0)
            row.concepts = state.get("concepts", row.concepts or {})
            # v3 opt-in goals/reflections (preserve existing when key absent).
            if "goals" in state:
                row.goals = state["goals"]
            if "reflections" in state:
                row.reflections = state["reflections"]
            # v4 opt-in per-learner customization overlay (preserve when key absent).
            if "overlay" in state:
                row.overlay = state["overlay"]
            s.commit()

    def append_event(self, event: dict) -> None:
        from .models import Event

        with self._Session() as s:
            s.add(
                Event(
                    participant_id=event["participant_id"],
                    exercise_id=event["exercise_id"],
                    mode=event["mode"],
                    event_type=event["event_type"],
                    stance=event.get("stance"),
                    payload=event["payload"],
                    note=event.get("note", ""),
                )
            )
            s.commit()

    def attempts(self, participant_id: str, exercise_id: str) -> int:
        from sqlalchemy import func, select

        from .models import Event

        with self._Session() as s:
            stmt = (
                select(func.count())
                .select_from(Event)
                .where(
                    Event.participant_id == participant_id,
                    Event.exercise_id == exercise_id,
                    Event.event_type == "run",
                )
            )
            return int(s.execute(stmt).scalar() or 0)

    def record_course_attempt(self, participant_id: str, exercise_id: str) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        from .models import CourseAttempt

        with self._Session.begin() as session:
            factory = (
                pg_insert
                if session.bind is not None and session.bind.dialect.name == "postgresql"
                else sqlite_insert
            )
            statement = factory(CourseAttempt).values(
                participant_id=participant_id, exercise_id=exercise_id, count=1
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[CourseAttempt.participant_id, CourseAttempt.exercise_id],
                    set_={"count": CourseAttempt.count + 1},
                )
            )

    def course_attempts(self, participant_id: str, exercise_id: str) -> int:
        from .models import CourseAttempt

        with self._Session() as session:
            row = session.get(CourseAttempt, (participant_id, exercise_id))
            return row.count if row else 0

    def export_jsonl(self, participant_id: str | None = None) -> str:
        from sqlalchemy import select

        from .models import Event

        with self._Session() as s:
            stmt = select(Event).order_by(Event.ts)
            if participant_id:
                stmt = stmt.where(Event.participant_id == participant_id)
            rows = s.execute(stmt).scalars().all()
            return "\n".join(
                json.dumps(
                    {
                        "participant_id": r.participant_id,
                        "ts": r.ts.isoformat(),
                        "exercise_id": r.exercise_id,
                        "mode": r.mode,
                        "event_type": r.event_type,
                        "stance": r.stance,
                        "payload": r.payload,
                        "note": r.note,
                    }
                )
                for r in rows
            )
