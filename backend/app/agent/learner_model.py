"""
Deterministic per-concept learner-model update and due-review logic.

Companion to agent/memory.py: memory merges the free-text grasped/shaky tags
the Reasoner emits; this module maintains a structured per-concept mastery map
that the Planner uses for spaced follow-up (revisit moves).

Concept-entry shape (one key per concept_id in LearnerState.concepts):
    {
        "state":          "shaky" | "grasped",
        "evidence":       int,          # times this concept was touched
        "last_seen":      iso_str,      # last exercise that touched it
        "last_review":    iso_str | None,
        "last_review_ex": str | None,   # exercise_id of last revisit turn
    }

Grasped sticks once evidence ≥ 2 — a single solve isn't enough to override a
persistent misconception signal, but two independent solves are.
"""
from __future__ import annotations

from datetime import UTC, datetime

from ..core.domain import get_active_pack


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_entry(now: str) -> dict:
    return {
        "state": "shaky",
        "evidence": 0,
        "last_seen": now,
        "last_review": None,
        "last_review_ex": None,
    }


def update_concepts(
    prev: dict,
    *,
    exercise_id: str,
    result: dict,
    misconception_id: str | None,
    repeated_error: bool,
    now: str | None = None,
    revisit_concept: str | None = None,
    taxonomy=None,
) -> dict:
    """Return an updated concepts dict (does not mutate prev).

    Rules (applied in sequence):
      1. Touch the exercise's own concept: evidence += 1, last_seen = now.
      2. result.goal_met → that concept state = "grasped".
      3. misconception_id → MISCONCEPTION_CONCEPT[mid] state = "shaky"
         (unless already grasped with evidence ≥ 2 — grasped sticks at that point).
      4. repeated_error (no solve) → exercise's concept state = "shaky"
         (same grasped-sticks guard applies).
      5. revisit_concept → update last_review = now, last_review_ex = exercise_id.
    """
    if now is None:
        now = _now_iso()
    if taxonomy is None:
        taxonomy = get_active_pack().taxonomy

    concepts = {k: dict(v) for k, v in prev.items()}
    own_cid = taxonomy.concept_for_exercise(exercise_id)
    goal_met = isinstance(result, dict) and bool(
        result.get("goal_met") or result.get("goalMet")
    )

    # 1. Touch the exercise's own concept.
    if own_cid:
        entry = dict(concepts.get(own_cid, _default_entry(now)))
        entry["evidence"] = entry.get("evidence", 0) + 1
        entry["last_seen"] = now
        concepts[own_cid] = entry

    # 2. Solve → grasped.
    if goal_met and own_cid:
        concepts[own_cid]["state"] = "grasped"

    # 3. Misconception → shaky (unless firmly grasped).
    if misconception_id:
        mcid = taxonomy.concept_for_misconception(misconception_id)
        if mcid:
            entry = dict(concepts.get(mcid, _default_entry(now)))
            firmly_grasped = (
                entry.get("state") == "grasped" and entry.get("evidence", 0) >= 2
            )
            if not firmly_grasped:
                if mcid not in concepts:
                    entry["evidence"] = 1
                    entry["last_seen"] = now
                entry["state"] = "shaky"
                concepts[mcid] = entry

    # 4. Repeated error (no solve) → own concept shaky.
    if repeated_error and not goal_met and own_cid:
        entry = dict(concepts[own_cid])
        firmly_grasped = (
            entry.get("state") == "grasped" and entry.get("evidence", 0) >= 2
        )
        if not firmly_grasped:
            entry["state"] = "shaky"
            concepts[own_cid] = entry

    # 5. Revisit → update review metadata.
    if revisit_concept and revisit_concept in concepts:
        entry = dict(concepts[revisit_concept])
        entry["last_review"] = now
        entry["last_review_ex"] = exercise_id
        concepts[revisit_concept] = entry

    return concepts


def due_review(concepts: dict, exercise_id: str, taxonomy=None) -> list[str]:
    """Concept ids that are due for a spaced revisit on this exercise.

    A concept is due iff:
      - state == "shaky"
      - it is in taxonomy.relevant_concepts(exercise_id)  (it matters here)
      - last_review_ex != exercise_id            (not already revisited on this exercise)
    """
    if taxonomy is None:
        taxonomy = get_active_pack().taxonomy
    rel = taxonomy.relevant_concepts(exercise_id)
    result = []
    for cid in rel:
        entry = concepts.get(cid)
        if entry is None:
            continue
        if entry.get("state") != "shaky":
            continue
        if entry.get("last_review_ex") == exercise_id:
            continue
        result.append(cid)
    return result
