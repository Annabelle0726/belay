"""
Distress-routing layer of the wellbeing floor (Slice G).

This is the THIRD layer of the wellbeing floor, and it is different in kind from the
other two (Slice D): the intake `goals.is_harmful` detector guards against the learner
asking the tutor to be unkind, and `governance.soften_if_berating` guards the tutor's
own tone. THIS layer reads the LEARNER'S message for an explicit distress signal and,
when routing is enabled, routes OUTWARD to a human instead of tutoring.

Hard boundaries (non-negotiable):
  - Detection is a ROUTING TRIGGER, not a mental-health judgment. It never scores
    severity, never diagnoses, and names no methods.
  - The response surfaces INSTITUTION-CONFIGURED support and routes to a human. The
    framework ships a neutral frame only; it invents no hotline, number, or service.
  - No verbatim distressing content and no PII is stored, logged, or traced.
  - Off by default (`settings.distress_routing_enabled`); when off, none of this runs.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

log = logging.getLogger("peer_tutor.distress")

# CONSERVATIVE, EXPLICIT-CRISIS-ONLY starter vocabulary.
#
# IRB-REVIEW-REQUIRED and tunable (extend via config DISTRESS_SIGNAL_TERMS). This is a
# narrow routing trigger for explicit self-harm / suicidal-ideation phrasing ONLY. It
# MUST NOT fire on generalized academic despair or frustration ("I want to give up on
# this degree", "I feel hopeless about this course") — those are normal struggle, and
# routing them to crisis support would itself be a harm (pathologizing). The detection
# boundary between academic despair and crisis is a standing IRB/product decision; this
# default list is deliberately minimal and high-precision. It names no methods and
# scores no severity. False positives route to support (the low-harm direction).
_DEFAULT_TERMS = (
    r"kill(?:ing)?\s+myself",
    r"\bsuicid(?:e|al)\b",
    r"want\s+to\s+die",
    r"end(?:ing)?\s+my\s+life",
    r"take\s+my\s+(?:own\s+)?life",
    r"don'?t\s+want\s+to\s+(?:be\s+alive|live)",
    r"(?:hurt|harm)\s+myself",
    r"self[\s-]?harm",
    r"no\s+reason\s+to\s+live",
    r"better\s+off\s+dead",
)
_DISTRESS = re.compile("|".join(_DEFAULT_TERMS), re.IGNORECASE)


def has_distress_signal(text: str, extra_terms: Iterable[str] | None = None) -> bool:
    """True iff ``text`` carries an explicit distress signal (a routing trigger, not a
    judgment). ``extra_terms`` are institution-configured additional whole-text patterns
    (IRB-owned), matched case-insensitively as literals."""
    if not text:
        return False
    if _DISTRESS.search(text):
        return True
    for t in extra_terms or ():
        t = (t or "").strip()
        if t and re.search(re.escape(t), text, re.IGNORECASE):
            return True
    return False


# --- the safe response frame (framework-neutral scaffolding; content is config) -----
# Warm, brief, non-amplifying. States the tutor is a study tool not a counselor, points
# the learner OUTWARD to a human, does not counsel/diagnose/assess/name methods, and
# does not isolate ("you don't have to deal with this alone" points outward).
_FRAME_HEAD = (
    "I want to pause our work for a moment. I'm a study tool, not a "
    "counselor, and what you're describing deserves real support from a person."
)


def distress_frame(configured: bool, support_message: str, escalation_target: str) -> str:
    """Build the learner-facing distress frame. Content is gated on ``configured``:
    when the institution has filled in its resources, surface them and name the
    escalation route; otherwise render a SAFE GENERIC frame that renders NO placeholder.
    The FILL-IN default is never shown to a learner."""
    if configured:
        return (
            f"{_FRAME_HEAD} {support_message}\n\n"
            f"I'm also flagging this so a person can reach out to you: {escalation_target}"
        )
    return (
        f"{_FRAME_HEAD} Please reach out to someone you trust, or your institution's "
        "support channels, as soon as you can — you don't have to deal with this alone."
    )


def frame_from_settings(settings) -> str:
    """The distress frame from current config, logging an operator warning (no PII, no
    learner text) when routing is enabled but not configured."""
    configured = settings.distress_configured
    if not configured:
        log.warning(
            "DISTRESS_ROUTING_ENABLED is on but DISTRESS_SUPPORT_MESSAGE / "
            "DISTRESS_ESCALATION_TARGET are still the [FILL-IN] defaults; rendering the "
            "safe generic frame. Set both to your institution's IRB-approved values."
        )
    return distress_frame(
        configured, settings.distress_support_message, settings.distress_escalation_target
    )


def extra_terms(settings) -> tuple:
    """Institution-configured extra detection terms (comma-separated), IRB-owned."""
    raw = getattr(settings, "distress_signal_terms", "") or ""
    return tuple(t.strip() for t in raw.split(",") if t.strip())
