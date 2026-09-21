# SPDX-License-Identifier: Apache-2.0
"""Normalization of the client's `recent` dialogue window — shared by both HTTP edges.

Every edge that accepts a turn (the host-facing `/api/sol/turn` and the pseudonymous
`/quad/v1/turn` sidecar) receives the same transcript window and must hand the agent
loop the same internal vocabulary: ``{"who": "student" | <persona id>, "text": ...}``.

Two things make this worth a shared, carefully-documented helper rather than a
per-edge model:

1. Two spellings are live at once. The canonical wire shape is
   ``{"role": "user"|"assistant", "content": ...}``; the older
   ``{"who": "student"|"tutor", "text": ...}`` is still sent by browser clients that
   shipped before the rename and may be cached in a host page.

2. The history is *evidence*, not decoration. `context._student_wants_reflect`,
   `context._latest_student_message` and `governance._student_asked_for_answer` read
   the student's latest turn to decide reflect-routing, distress routing and the
   answer-seeking trip. So an entry that cannot be labelled is DROPPED, never
   guessed: coercing a mislabelled turn into student speech could look for an
   answer-seeking cue in the tutor's own words, and defaulting to ``student`` is the
   unsafe direction. Dropping is also the kinder failure for the learner — one bad
   history line must not cost them the turn they are waiting on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STUDENT = "student"
"""Internal `who` for the learner. Never a persona id: the floors look for this."""

#: Raw-history spelling -> canonical wire role.
ROLE_ALIASES: dict[str, str] = {
    "user": "user",
    "student": "user",
    "learner": "user",
    "assistant": "assistant",
    "sol": "assistant",
    "tutor": "assistant",
    "system": "assistant",
}


@dataclass(frozen=True)
class Turn:
    """One normalized dialogue turn.

    ``role`` is the canonical wire role (``"user"`` | ``"assistant"``);
    ``content`` is the turn text.
    """

    role: str
    content: str

    @property
    def who(self) -> str:
        """The internal `who`: ``"student"`` for the learner, else the caller substitutes
        the active pack's persona id (this module is persona-agnostic and never names
        one)."""
        return STUDENT if self.role == "user" else "assistant"

    def as_dialogue(self, persona_id: str) -> dict[str, str]:
        """The agent layer's `recent_dialogue` entry."""
        return {"who": self.who if self.role == "user" else persona_id, "text": self.content}


def coerce_recent_turns(raw: Any) -> list[Turn]:
    """Normalize a client's `recent` window onto `Turn`, dropping what cannot be labelled.

    Accepts both spellings (see the module docstring). A non-list, a non-object entry,
    an entry with no role, or an entry whose role is not in `ROLE_ALIASES` is dropped.
    """
    if not isinstance(raw, list):
        return []
    turns: list[Turn] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_role = item.get("role", item.get("who"))
        raw_text = item.get("content", item.get("text", ""))
        if raw_role is None:
            continue
        role = ROLE_ALIASES.get(str(raw_role).strip().lower())
        if role is None:
            continue
        turns.append(Turn(role=role, content="" if raw_text is None else str(raw_text)))
    return turns


def to_dialogue(raw: Any, persona_id: str) -> list[dict[str, str]]:
    """Convenience: a raw window straight to the agent layer's vocabulary."""
    return [t.as_dialogue(persona_id) for t in coerce_recent_turns(raw)]
