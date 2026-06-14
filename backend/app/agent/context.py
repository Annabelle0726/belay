"""
Per-turn context assembly.

Every component reasons over the same grounded snapshot of the student's
situation. This mirrors the artifact's buildContext() so behavior is continuous
with the validated prototype, but it is built server-side from the persistent
learner model + the request.

F6 addition: for peer and oracle stances (shared capability), the context now
includes a compact misconception map — expectations + {id, belief, signature,
peer_move} for each likely misconception.  The control arm short-circuits before
any reasoner call, so it never sees this map.
"""
from __future__ import annotations

import json
from typing import Optional

from ..core.domain import get_active_pack


def _last_result(result: Optional[dict]) -> object:
    if not result:
        return "no run yet"
    if not result.get("ok"):
        return {"compiles": False, "error": result.get("error"), "goal_met": False,
                "metric": None, "summary": None}
    # Pack-agnostic (§6): the per-pack human-readable detail is in result.pack.summary
    # (quantum: distribution + mismatch; DS: check results). Fall back to the legacy
    # quantum dist/diff so pre-v6 payloads still render something useful.
    pack_env = result.get("pack") or {}
    summary = pack_env.get("summary")
    if summary is None and (pack_env.get("dist") or result.get("dist") or result.get("diff")):
        dist = pack_env.get("dist") or result.get("dist") or []
        diff = pack_env.get("diff") or result.get("diff") or ""
        dist_str = ", ".join(f"{d['bits']}:{round(d['p'] * 100)}%" for d in dist)
        summary = f"{diff} {dist_str}".strip()
    return {
        "compiles": True,
        "error": None,
        "goal_met": result.get("goalMet", False),
        "metric": result.get("metric"),
        "summary": summary,
    }


def default_signals(attempts: int) -> dict:
    return {"attempts": attempts, "distanceTrend": [], "repeatedError": False,
            "sinceLastProgress": 0}


def _misconceptions_context(exercise_id: str) -> dict:
    """Compact rendering for the Peer-Reasoner: expectations + terse misconception
    list (id, belief, signature, peer_move).  inventory_seed is omitted — it is
    only needed for the concept-inventory tool, not for the reasoner."""
    entry = get_active_pack().misconceptions().for_exercise(exercise_id)
    return {
        "expectations": entry["expectations"],
        "misconceptions": [
            {
                "id":        m["id"],
                "belief":    m["belief"],
                "signature": m["signature"],
                "peer_move": m["peer_move"],
            }
            for m in entry["misconceptions"]
        ],
    }


def build_context(payload: dict, learner_state: dict, attempts: int) -> dict:
    ex = payload["exercise"]
    stance = payload.get("stance", "peer")
    ctx: dict = {
        "event": payload.get("event", "chat"),                 # run | chat
        "mode": payload.get("mode", "study"),                  # study | teach
        "exercise": {
            "title": ex["title"], "concept": ex["concept"],
            "goal": ex["goalText"], "prompt": ex["prompt"],
        },
        "current_functional_model": payload.get("source", ""),
        "last_result": _last_result(payload.get("result")),
        "attempt_signals": payload.get("signals") or default_signals(attempts),
        "known_memory": {"grasped": learner_state.get("grasped", []),
                         "shaky": learner_state.get("shaky", [])},
        "recent_dialogue": payload.get("recent", []),
    }
    # Shared capability (F6): inject misconception expectations + signatures for
    # the peer and oracle stances so both arms have the same tutor knowledge.
    # Control short-circuits in the orchestrator before the reasoner runs, so
    # this key is deliberately absent there.
    if stance != "control":
        ctx["misconceptions_context"] = _misconceptions_context(ex.get("id", ""))

    # Persistent learner model: spaced follow-up (revisit) — peer/oracle only.
    if stance != "control":
        from . import learner_model as lm_mod
        taxonomy = get_active_pack().taxonomy
        concepts = learner_state.get("concepts", {})
        due = lm_mod.due_review(concepts, ex.get("id", ""))
        ctx["due_review"] = [{"id": cid, "label": taxonomy.label(cid)} for cid in due]
        shaky_cids = [cid for cid, v in concepts.items() if v.get("state") == "shaky"]
        grasped_cids = [cid for cid, v in concepts.items() if v.get("state") == "grasped"]
        ctx["concept_model"] = {"n_shaky": len(shaky_cids), "n_grasped": len(grasped_cids)}

    return ctx


def serialize(ctx: dict) -> str:
    return json.dumps(ctx, indent=2, ensure_ascii=False)
