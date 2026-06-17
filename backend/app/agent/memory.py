"""
Memory component.

Persists the learner model across turns and sessions: it merges the grasped /
shaky concept tags proposed this turn into the running lists held in the store,
AND updates the structured per-concept mastery map (LearnerState.concepts).

This is the difference between a stateless demo and a system that can target
support to a student over time (and supply the longitudinal signal §5e needs).
"""

from __future__ import annotations

from ..store import Store, merge_memory
from . import learner_model as lm_mod


def update(
    store: Store,
    participant_id: str,
    draft: dict,
    *,
    exercise_id: str,
    result: dict,
    misconception_id: str | None,
    repeated_error: bool,
    plan: dict,
) -> dict:
    prev = store.get_learner_state(participant_id)
    merged = merge_memory(
        prev, {"grasped": draft.get("grasped", []), "shaky": draft.get("shaky", [])}
    )
    new_concepts = lm_mod.update_concepts(
        prev.get("concepts", {}),
        exercise_id=exercise_id,
        result=result,
        misconception_id=misconception_id,
        repeated_error=repeated_error,
        revisit_concept=plan.get("revisit_concept"),
    )
    state = {
        "grasped": merged["grasped"],
        "shaky": merged["shaky"],
        "attempts": prev.get("attempts", 0),
        "concepts": new_concepts,
        # Preserve the opt-in goals/reflections/overlay across a turn (never clobbered
        # here): they are per-learner customization, not concept memory this turn touches.
        "goals": prev.get("goals"),
        "reflections": prev.get("reflections", []),
        "overlay": prev.get("overlay"),
    }
    store.save_learner_state(participant_id, state)
    return state
