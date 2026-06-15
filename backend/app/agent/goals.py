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

from ..store import make_event

# Wellbeing floor (Slice B; broadened here): a deterministic, cautious detector for
# self-destructive / berating self-rules. A student goal that directs the tutor to
# harm, demean, or grind the student is RECORDED but marked not-honored; the persona
# stance forbids it and a student goal cannot override the stance.
#
# IMPORTANT — this is a PRE-HOC heuristic, NOT an oracle-backed gate. Tone has no
# ground-truth oracle the way leak-detection does (the grader + the known solution),
# so this detector has FALSE NEGATIVES by nature: a harmful goal can be phrased to
# evade it. It is therefore biased CAUTIOUS — a false positive routes a benign goal
# to the kind decline (acceptable); a false negative would honor a harmful goal (not
# acceptable) — and it is only one layer of the wellbeing floor (see
# `prompts._goals_block` never-honor-framing and `governance.soften_if_berating`).
# The asymmetry vs. the leak gate is documented in docs/EXTRACTION_PLAN.md §(g).
_HARMFUL = re.compile(
    # direct insults / name-calling directed at the student
    r"(call me\s+(an?\s+)?(idiot|stupid|dumb|moron|loser|failure|fool)"
    r"|tell me\s+(that\s+)?(i'?m|i am)\s+(an?\s+)?(stupid|dumb|idiot|moron|worthless|"
    r"useless|pathetic|a\s+failure|a\s+loser|trash|garbage|an?\s+idiot|hopeless|behind|slow)"
    r"|(berate|insult|demean|humiliate|belittle|mock|ridicule|degrade|shame)\s+me"
    r"|be\s+(mean|cruel|harsh|nasty|brutal|rude|savage|ruthless)\b"
    r"|make me feel\s+(bad|stupid|worthless|terrible|awful|small|guilty)"
    r"|punish me|i hate myself|tell me i suck|i deserve to\s+(fail|suffer)"
    r"|i'?m\s+(stupid|worthless|useless|a\s+failure)"
    # negative self-talk invitations: ask the tutor to confirm/agree with self-deprecation
    r"|(agree|confirm)\s+(with me\s+)?(that\s+)?(i'?m|i am)\s+"
    r"(stupid|dumb|bad|worthless|useless|hopeless|a\s+failure|behind|slow)"
    r"|remind me\s+(that\s+|how\s+|of how\s+)?(i'?m|i am|stupid|dumb|bad|behind|slow|"
    r"worthless|useless|hopeless|i('?ll| will) never)"
    r"|tell me\s+i('?ll| will) never\b|say\s+i('?ll| will) never\b"
    r"|point out\s+(how\s+(far\s+)?)?(dumb|stupid|bad|behind|slow|much\s+i)\b"
    r"|rub it in|tear me\s+(down|apart)|put me down"
    # self-deprecation / guilt requests
    r"|guilt[\s-]?trip me|make me feel guilty|shame me\s+(into|when|if|for)"
    # pressure-to-overwork framings (require an overwork object so we don't catch
    # benign "push me to think harder")
    r"|(never|don'?t|do not)\s+let me\s+(rest|stop|quit|sleep|take a break|breathe)"
    r"|(make me|i'?ll)\s+(work|study|grind|push)\s+"
    r"(all night|nonstop|24/?7|around the clock|without (a |any )?(break|rest|sleep))"
    r"|no\s+(breaks|rest|sleep)\b"
    r"|push me\s+(until|till|til)\s+i\s+(cry|break|burn ?out|drop|collapse|quit)"
    r"|work me\s+(to the bone|until i)\b)",
    re.IGNORECASE,
)


def is_harmful(text: str) -> bool:
    """True iff the goal directs the tutor to harm/berate/grind the student.

    A cautious PRE-HOC heuristic (not an oracle). See the module note on the
    leak-floor vs. wellbeing-floor asymmetry: this WILL have false negatives, which
    is why it is one of several wellbeing protections, never a single gate.
    """
    return bool(_HARMFUL.search(text or ""))


# FLAGGED DECISION (NOT implemented here) — distress response.
# Goals/reflection intake is a place a student may express genuine DISTRESS, not
# merely a counterproductive rule. How the tutor should respond to a distress-
# signaling goal/reflection is a PRODUCT + IRB decision, deliberately left to whoever
# owns that call. Safe defaults recorded for them (see docs/EXTRACTION_PLAN.md §(g)):
# do NOT honor a harmful directive; respond briefly and kindly WITHOUT reinforcing or
# amplifying the distress; do NOT diagnose; leave deeper support to humans and the
# institution's channels; whether to surface any support resource is a deliberate
# choice, not a default. No speculative distress handling is built.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(store, participant_id: str, event_type: str, payload: dict) -> None:
    """Append an additive §6 audit event (goal_set / reflection_recorded). Never
    let an audit write break the intake (e.g. an FK miss on an unregistered pid)."""
    try:
        store.append_event(make_event(participant_id, "", "study", event_type, payload))
    except Exception:
        pass


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
        _emit(store, participant_id, "goal_set",
              {"text": None, "honored": None, "action": "clear"})
        return None
    # Wellbeing floor: a self-destructive/berating goal is recorded but NOT honored.
    honored = not is_harmful(text)
    artifact = {"text": text, "ts": _now_iso(), "honored": honored}
    if not honored:
        artifact["floor"] = "wellbeing"
    state["goals"] = artifact
    store.save_learner_state(participant_id, state)
    _emit(store, participant_id, "goal_set",
          {"text": text, "honored": honored, "action": "set"})
    return artifact


def clear_goals(store, participant_id: str) -> None:
    set_goals(store, participant_id, "")


def add_reflection(store, participant_id: str, text: str,
                   concept: Optional[str] = None) -> Optional[dict]:
    """Store a student reflection (their own words), timestamped and LINKED to the
    goal currently in force. Reflections feed the tutor's read of the student (the
    learner model) and are never surfaced to an instructor."""
    text = (text or "").strip()
    if not text:
        return None
    state = store.get_learner_state(participant_id)
    goal = state.get("goals") or {}
    goal_text = goal.get("text")
    reflection = {"text": text, "ts": _now_iso(), "goal_text": goal_text, "concept": concept}
    reflections = list(state.get("reflections") or [])
    reflections.append(reflection)
    state["reflections"] = reflections
    store.save_learner_state(participant_id, state)
    _emit(store, participant_id, "reflection_recorded",
          {"text": text, "goal_text": goal_text, "concept": concept})
    return reflection


def get_reflections(state: dict) -> list:
    return (state or {}).get("reflections") or []
