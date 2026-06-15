"""
Learner-authored goals (opt-in, single-learner).

The student's OWN words are stored as the honored directive — kept pseudonymously
on the learner model, never PII, never ranked or compared, never written to grades,
never surfaced to an instructor by default. With no goals set, behavior is exactly
what it is today.

Parsing is intentionally minimal: store the text + a timestamp; do not
over-structure. (Slice B adds a deterministic wellbeing-floor `honored` flag; the
governance leak gate is always supreme and is unaffected by goals.)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_goals(state: dict) -> Optional[dict]:
    """The current goals artifact ({text, ts, ...}) or None."""
    return (state or {}).get("goals")


def set_goals(store, participant_id: str, text: str) -> Optional[dict]:
    """Set/update the student's goals (empty text clears). Returns the artifact.

    Read-modify-write the full learner state so the goals column is updated
    without disturbing grasped/shaky/concepts/reflections.
    """
    text = (text or "").strip()
    state = store.get_learner_state(participant_id)
    if not text:
        state["goals"] = None
        store.save_learner_state(participant_id, state)
        return None
    artifact = {"text": text, "ts": _now_iso()}
    state["goals"] = artifact
    store.save_learner_state(participant_id, state)
    return artifact


def clear_goals(store, participant_id: str) -> None:
    set_goals(store, participant_id, "")
