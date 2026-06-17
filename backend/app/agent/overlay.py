"""
Per-learner customization overlay (opt-in, single-learner).

The seam that lets a host (or the learner) shape HOW the tutor helps, never WHAT it
withholds. It is the generalization of the Slice A-D goals discipline from one
free-text field to a small, BOUNDED set of preferences:

  - persona      : enumerated knobs (tone, verbosity, framing). NOT a free-form
                   stance string. A free-form stance is both a wellbeing-floor bypass
                   risk and a prompt-injection surface; enumerated knobs are safe by
                   construction (only a framework-authored phrase, keyed by the chosen
                   enum, ever reaches the prompt -- never the learner's raw text).
  - pedagogy     : enumerated knobs (scaffolding, stretch), defaulting mastery-friendly
                   and Goodhart-resistant. NO field reduces the leak floor or trades
                   mastery for answers ("less scaffolding" means more independence /
                   FEWER hints, NOT more of the answer).
  - accommodation: reading level + language. Rendering / prompt-level only; no
                   behavioral-floor implications.

Goals and reflection are the same per-learner surface and ride alongside the overlay
on the learner state (`agent/goals.py`); they keep their own intake for back-compat.

FLOOR ROUTING (the load-bearing piece). Every learner-supplied value is run through
the SAME wellbeing detector goals use (`goals.is_harmful`) at intake. A harm-requesting
field ("be harsh with me", "never let me rest") is RECORDED but marked not-honored and
dropped to its mastery-friendly default; it can only ever receive decline framing. The
leak gate and the wellbeing floor remain SUPREME and UN-customizable. Two reasons the
overlay is even safer than goals here:
  1. Enumeration: a value that is not a recognized enum token is dropped to the default,
     so a harmful free-text value cannot reach the prompt as honored instruction at all.
  2. Never-honor re-check: `prompts._overlay_block` re-checks each field's raw text and
     refuses honor framing if it requests harm, regardless of a stored honored flag.
The post-hoc berating softener (`governance.soften_if_berating`) remains the backstop
for a berating OUTPUT, exactly as for goals; tone has no oracle (EXTRACTION_PLAN §(g)).
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..store import make_event
from .goals import is_harmful

# --- bounded vocabularies (enumerated knobs) ---------------------------------
# Each knob maps {field: (allowed_values, default)}. Defaults are mastery-friendly
# and reproduce today's behavior, so an absent/empty overlay changes nothing.
_PERSONA = {
    "tone": (("warm", "neutral", "direct"), "warm"),  # "direct" == firm but kind
    "verbosity": (("brief", "balanced", "detailed"), "balanced"),
    "framing": (("peer", "coach"), "peer"),
}
_PEDAGOGY = {
    # "less" scaffolding = more independence / fewer hints, NEVER more of the answer.
    "scaffolding": (("more", "default", "less"), "default"),
    "stretch": (("low", "default", "high"), "default"),  # "high" == challenge me
}
_ACCOMMODATION = {
    "reading_level": (("plain", "default", "advanced"), "default"),
    # language is a short locale-ish token, validated by shape (prompt/rendering only).
    "language": (None, "en"),
}

_SECTIONS = {"persona": _PERSONA, "pedagogy": _PEDAGOGY, "accommodation": _ACCOMMODATION}


# A language code is a short alpha token (e.g. "en", "es", "pt-br"); anything else
# falls back to the default. Kept tiny on purpose (rendering/prompt-level only).
def _valid_language(v: str) -> bool:
    v = (v or "").strip().lower()
    return 0 < len(v) <= 12 and all(c.isalpha() or c == "-" for c in v)


def is_harmful_overlay(overlay: dict | None) -> bool:
    """True iff any raw value anywhere in a raw overlay requests harm (same detector
    as goals). Used at intake to route to decline; defensive, has false negatives."""
    if not overlay:
        return False
    for section in overlay.values():
        if isinstance(section, dict):
            for v in section.values():
                if isinstance(v, str) and is_harmful(v):
                    return True
        elif isinstance(section, str) and is_harmful(section):
            return True
    return False


def _normalize_field(field: str, raw, allowed, default) -> dict:
    """Resolve one knob to {value, raw, honored}. A harm-requesting raw value is
    declined (honored=False) and forced to the default; an unrecognized value also
    falls back to the default but stays honored (it just wasn't a known token)."""
    raw_str = raw if isinstance(raw, str) else None
    harmful = bool(raw_str and is_harmful(raw_str))
    if field == "language":
        ok = raw_str is not None and _valid_language(raw_str) and not harmful
        value = raw_str.strip().lower() if ok else default
    else:
        norm = raw_str.strip().lower() if raw_str else None
        value = norm if (norm in allowed and not harmful) else default
    return {"value": value, "raw": raw_str, "honored": not harmful}


def normalize_overlay(raw: dict | None) -> dict | None:
    """Validate a raw overlay into a bounded artifact, routing every value through the
    wellbeing floor. Returns None for an empty overlay (so no-overlay == today).

    Shape: {persona:{knob:{value,raw,honored}}, pedagogy:{...}, accommodation:{...},
            declined:[<"section.knob">...], ts}. Unknown sections/keys are ignored.
    """
    if not raw or not isinstance(raw, dict):
        return None
    artifact: dict = {"ts": _now_iso(), "declined": []}
    any_nondefault = False
    for sec_name, spec in _SECTIONS.items():
        sec_raw = raw.get(sec_name) or {}
        if not isinstance(sec_raw, dict):
            sec_raw = {}
        section: dict = {}
        for field, (allowed, default) in spec.items():
            f = _normalize_field(field, sec_raw.get(field), allowed, default)
            section[field] = f
            if not f["honored"]:
                artifact["declined"].append(f"{sec_name}.{field}")
            if f["value"] != default or f["raw"] is not None:
                any_nondefault = True
        artifact[sec_name] = section
    if not any_nondefault:
        return None
    return artifact


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _emit(store, participant_id: str, event_type: str, payload: dict) -> None:
    """Append an additive §6 audit event (overlay_set). Never let an audit write
    break intake (e.g. an FK miss on an unregistered pid)."""
    try:
        store.append_event(make_event(participant_id, "", "study", event_type, payload))
    except Exception:
        pass


def get_overlay(state: dict) -> dict | None:
    """The current customization overlay artifact, or None."""
    return (state or {}).get("overlay")


def set_overlay(store, participant_id: str, raw: dict | None) -> dict | None:
    """Set/replace the learner's customization overlay (None/empty clears). Returns
    the normalized artifact. Read-modify-write so goals/reflections/concepts are
    preserved. Emits an additive `overlay_set` event recording any declined fields."""
    artifact = normalize_overlay(raw)
    state = store.get_learner_state(participant_id)
    state["overlay"] = artifact
    store.save_learner_state(participant_id, state)
    _emit(
        store,
        participant_id,
        "overlay_set",
        {
            "declined": (artifact or {}).get("declined", []),
            "action": "set" if artifact else "clear",
        },
    )
    return artifact


def clear_overlay(store, participant_id: str) -> None:
    set_overlay(store, participant_id, None)
