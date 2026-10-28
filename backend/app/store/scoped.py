# SPDX-License-Identifier: AGPL-3.0-only
"""Scope the unchanged core store protocol to an authenticated class learner.

Class state: concepts, grasped/shaky, goals, reflections, overlay and total counters.
Assignment state: run attempts and exercise events, keyed by exercise + version.
"""

from __future__ import annotations

import json

from ..auth import Identity, denied
from .consent import ConsentRouter
from .repository import InMemoryStore, SqlStore, Store

_METRIC_KEYS = {
    "ok",
    "goalMet",
    "metric",
    "triggered",
    "configured",
    "routed",
    "honored",
    "alignment",
    "escalated",
    "abstained",
    "confidence",
    "confidence_trajectory",
    "planner",
    "reasoner",
    "self_eval",
    "timings_ms",
    "component_usage",
    "tokens_in",
    "tokens_out",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
    "cost_usd",
    "wall_ms",
    "elapsed_ms",
    "attempts",
    "count",
    "retrieved",
    "kept",
}


def _metrics(value):
    """Allowlisted, numeric/boolean telemetry; text and arbitrary keys are excluded."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {
            k: _metrics(v)
            for k, v in value.items()
            if k in _METRIC_KEYS and (isinstance(v, (dict, bool, int, float)) or v is None)
        }
    return None


class ScopedStore:
    def __init__(self, store: Store, identity: Identity, state_store: Store | None = None):
        self.store = store
        self.identity = identity
        self.state_store = state_store if state_store is not None else store

    def _pid(self, pid: str) -> str:
        if pid != self.identity.learner_id:
            raise denied()
        return self.identity.storage_id

    def _exercise(self, exercise_id: str) -> str:
        if not exercise_id:
            return ""  # class-level customization events
        if exercise_id != self.identity.exercise_id or not self.identity.exercise_version:
            raise denied()
        return self.identity.exercise_key(exercise_id, self.identity.exercise_version)

    def get_learner_state(self, participant_id: str) -> dict:
        return self.state_store.get_learner_state(self._pid(participant_id))

    def save_learner_state(self, participant_id: str, state: dict) -> None:
        self.state_store.save_learner_state(self._pid(participant_id), state)

    def append_event(self, event: dict) -> None:
        row = dict(event)
        row["participant_id"] = self._pid(event["participant_id"])
        row["exercise_id"] = self._exercise(event["exercise_id"])
        # The old core traces include source/dialogue and intake text. At the HTTP
        # persistence boundary retain only content-free signals; state remains private.
        payload = event["payload"]
        signals = payload.get("telemetry", payload.get("result", payload))
        row["payload"] = {
            "metrics": _metrics(signals),
            "exercise_version": self.identity.exercise_version if row["exercise_id"] else None,
        }
        row["note"] = ""
        if event["event_type"] == "run" and isinstance(self.state_store, (SqlStore, InMemoryStore)):
            self.state_store.record_course_attempt(row["participant_id"], row["exercise_id"])
        self.store.append_event(row)

    def attempts(self, participant_id: str, exercise_id: str) -> int:
        pid, exercise = self._pid(participant_id), self._exercise(exercise_id)
        if isinstance(self.state_store, (SqlStore, InMemoryStore)):
            return self.state_store.course_attempts(pid, exercise)
        return self.store.attempts(pid, exercise)

    def export_jsonl(self, participant_id: str | None = None) -> str:
        pid = self._pid(participant_id or self.identity.learner_id)
        allowed = {
            self.identity.exercise_key(ex, v): (ex, v) for ex, v in self.identity.assignments
        }
        rows = []
        for line in self.store.export_jsonl(pid).splitlines():
            row = json.loads(line)
            ex = row["exercise_id"]
            if ex and ex not in allowed:
                continue
            row["participant_id"] = self.identity.learner_id
            row["exercise_id"] = allowed[ex][0] if ex else ""
            rows.append(json.dumps(row))
        return "\n".join(rows)


def scoped_store(router: ConsentRouter, identity: Identity) -> ScopedStore:
    anon = identity.exercise_key(identity.storage_id, "consent")[:32]
    router.ensure_course_participant(identity.storage_id, anon)
    return ScopedStore(router.store_for(identity.storage_id), identity, router.durable)


def register(router: ConsentRouter, identity: Identity, consent: bool) -> None:
    # A second domain-separated digest satisfies the legacy unique anon_code column
    # without collisions between institutions/classes using the same learner alias.
    anon = identity.exercise_key(identity.storage_id, "consent")[:32]
    router.register_participant(identity.storage_id, anon, consent)
