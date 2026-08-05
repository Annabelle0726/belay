# SPDX-License-Identifier: AGPL-3.0-only
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
import re

from ..core.registry import get_active_pack

# Student-initiated reflect: an explicit cue in the latest student message.
_REFLECT_CUE = re.compile(
    r"\b(let'?s reflect|i want to reflect|can we reflect|reflect on (my|the) (goal|progress)"
    r"|how am i doing|am i on track|check in on (my|the) goal)\b",
    re.IGNORECASE,
)


def _student_wants_reflect(recent: list) -> bool:
    for turn in reversed(recent or []):
        if turn.get("who") == "student":
            return bool(_REFLECT_CUE.search(turn.get("text", "")))
    return False


# Retrieval-augmented context (Slice F): how many candidates to pull per turn.
_RETRIEVAL_K = 4


def _latest_student_message(recent: list) -> str:
    """The most recent student utterance (the retrieval query signal), or ''."""
    for turn in reversed(recent or []):
        if turn.get("who") == "student":
            return (turn.get("text") or "").strip()
    return ""


def _last_result(result: dict | None) -> object:
    if not result:
        return "no run yet"
    if not result.get("ok"):
        return {
            "compiles": False,
            "error": result.get("error"),
            "goal_met": False,
            "metric": None,
            "summary": None,
        }
    # Pack-agnostic (§6): the per-pack human-readable detail is in result.pack.summary
    # (e.g. the DS pack's check results). Fall back to the legacy dist/diff fields so
    # pre-v6 payloads (an older envelope shape) still render something useful.
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
    return {
        "attempts": attempts,
        "distanceTrend": [],
        "repeatedError": False,
        "sinceLastProgress": 0,
    }


def _misconceptions_context(exercise_id: str) -> dict:
    """Compact rendering for the Peer-Reasoner: expectations + terse misconception
    list (id, belief, signature, peer_move).  inventory_seed is omitted — it is
    only needed for the concept-inventory tool, not for the reasoner."""
    entry = get_active_pack().misconceptions().for_exercise(exercise_id)
    return {
        "expectations": entry["expectations"],
        "misconceptions": [
            {
                "id": m["id"],
                "belief": m["belief"],
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
        "event": payload.get("event", "chat"),  # run | chat
        "mode": payload.get("mode", "study"),  # study | teach
        "exercise": {
            "title": ex["title"],
            "concept": ex["concept"],
            "goal": ex["goalText"],
            "prompt": ex["prompt"],
        },
        "current_functional_model": payload.get("source", ""),
        "last_result": _last_result(payload.get("result")),
        "attempt_signals": payload.get("signals") or default_signals(attempts),
        "known_memory": {
            "grasped": learner_state.get("grasped", []),
            "shaky": learner_state.get("shaky", []),
        },
        "recent_dialogue": payload.get("recent", []),
    }
    # Opt-in learner-authored goals (the student's own words). Injected into the
    # persona-parameterized prompts (reasoner especially) as goals the tutor honors
    # within its stance — never as authority over the stance. Absent for control.
    if stance != "control":
        ctx["goals"] = learner_state.get("goals")
        # Per-learner customization overlay (bounded knobs). Injected into the
        # persona-parameterized prompts as preferences honored WITHIN the stance,
        # never as authority over it. Absent for control.
        ctx["overlay"] = learner_state.get("overlay")
        ctx["reflections"] = (learner_state.get("reflections") or [])[
            -3:
        ]  # recent, for the tutor's read
        # Student-initiated reflect: an explicit `request: "reflect"` or a dialogue cue.
        ctx["reflect_requested"] = bool(
            payload.get("request") == "reflect" or _student_wants_reflect(payload.get("recent", []))
        )
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

    # Retrieval-augmented context (Slice F) — peer/oracle only, and ONLY when the
    # pack ships a KnowledgeBase AND the student has actually asked something (the
    # query signal). Every candidate passage is screened by the CORE governance leak
    # gate (reusing pack.leak_evidence) BEFORE it can enter the prompt; only survivors
    # land in ctx["knowledge"]. The screening summary (counts + dropped ids/reasons,
    # never passage text) rides in ctx["_retrieval"] for the orchestrator to trace.
    # When knowledge() is None or there is no student query, no retrieval runs and the
    # context is byte-identical to before.
    #
    # Since the verifier-contract port, `screen_passages` is a CALLER-SIDE FAN-OUT
    # (SPEC.md §9 in the sibling verifier-contract repo): it loops over passages and
    # calls the SAME `leak` profile the draft gate calls, once per passage, with the
    # passage id riding in `context.subject_id`. It is deliberately not a second
    # profile and not a second reason code. The fan-out lives on this side of the
    # call — the contract verifies exactly one candidate per invocation — and so does
    # everything below: which passages were retrieved, how many, which survived, and
    # what goes in the trace are decisions the verifier never sees.
    if stance != "control":
        kb = get_active_pack().knowledge()
        student_msg = _latest_student_message(payload.get("recent", []))
        if kb is not None and student_msg:
            from . import governance as _gov

            query = " ".join(
                s for s in (student_msg, ex.get("concept", ""), ex.get("title", "")) if s
            )
            screen = _gov.screen_passages(kb.search(query, _RETRIEVAL_K), ex)
            ctx["knowledge"] = [
                {"id": p.id, "text": p.text, "citation": p.citation, "locator": p.locator}
                for p in screen["kept"]
            ]
            ctx["_retrieval"] = {
                "exercise_id": ex.get("id", ""),
                "retrieved": screen["retrieved"],
                "kept": [p.id for p in screen["kept"]],
                "dropped": screen["dropped"],  # [{id, reason}] — never passage text
            }

    return ctx


def serialize(ctx: dict) -> str:
    return json.dumps(ctx, indent=2, ensure_ascii=False)
