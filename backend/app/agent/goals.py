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

import re
from datetime import datetime, timezone
from typing import Optional

# Wellbeing floor (Slice B): a deterministic, cautious detector for self-destructive
# / berating self-rules. A student goal that directs the tutor to harm or demean the
# student is RECORDED but marked not-honored; the persona stance forbids it and a
# student goal cannot override the stance. Biased to decline: a false positive
# declines a borderline goal (safe); a false negative would license harm (not safe).
_HARMFUL = re.compile(
    r"(call me\s+(an?\s+)?(idiot|stupid|dumb|moron|loser|failure|fool)"
    r"|tell me\s+(that\s+)?(i'?m|i am)\s+(an?\s+)?(stupid|dumb|idiot|moron|worthless|"
    r"useless|pathetic|a\s+failure|a\s+loser|trash|garbage|an?\s+idiot)"
    r"|(berate|insult|demean|humiliate|belittle|mock|ridicule|degrade|shame)\s+me"
    r"|be\s+(mean|cruel|harsh|nasty|brutal|rude)\b"
    r"|make me feel\s+(bad|stupid|worthless|terrible|awful|small)"
    r"|punish me|i hate myself|tell me i suck|i deserve to\s+(fail|suffer)"
    r"|i'?m\s+(stupid|worthless|useless|a\s+failure))",
    re.IGNORECASE,
)


def is_harmful(text: str) -> bool:
    """True iff the goal directs the tutor to harm/berate the student (wellbeing floor)."""
    return bool(_HARMFUL.search(text or ""))


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
    # Wellbeing floor: a self-destructive/berating goal is recorded but NOT honored.
    honored = not is_harmful(text)
    artifact = {"text": text, "ts": _now_iso(), "honored": honored}
    if not honored:
        artifact["floor"] = "wellbeing"
    state["goals"] = artifact
    store.save_learner_state(participant_id, state)
    return artifact


def clear_goals(store, participant_id: str) -> None:
    set_goals(store, participant_id, "")
