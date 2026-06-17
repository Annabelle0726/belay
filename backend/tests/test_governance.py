"""Governance tests (DS fixtures) — the leak gate is the safety-critical piece,
so it gets the most direct coverage. Covers BOTH leak evidence sources:
the executable oracle (code that grades as a solution) AND prose disclosure
(EXTRACTION_PLAN §(f)), plus stance-conditional blocking and answer-seeking."""

from app.agent import governance
from app.core.registry import get_active_pack
from app.packs.datascience.solutions import SOLUTIONS

EX = get_active_pack().get_exercise("ds-foundations")

# A fenced, full working solution → executable oracle flags it.
_FULL_SOLUTION = "here you go:\n```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```"
# Prose that discloses the answer without any runnable code block.
_PROSE_LEAK = (
    "Honestly the answer is just to group by category and take the mean — "
    "you'll get 15, 40, and 100."
)


def _ctx(message_recent=None):
    return {
        "_exercise_full": EX,
        "recent_dialogue": message_recent or [],
        "exercise": {"concept": EX["concept"]},
    }


def test_blocks_full_solution_in_code_block():
    draft = {"message": _FULL_SOLUTION, "confidence": 0.95}
    gov = governance.check(_ctx(), {"intervention": "diagnose"}, draft, {})
    assert gov["block"] is True
    assert gov["flag"] == "withholding_solution"


def test_blocks_prose_disclosure():
    """Prose that discloses the answer (no code) is still blocked — the §(f) gap."""
    draft = {"message": _PROSE_LEAK, "confidence": 0.9}
    gov = governance.check(_ctx(), {"intervention": "co_reason"}, draft, {})
    assert gov["block"] is True
    assert gov["flag"] == "withholding_solution"


def test_allows_genuine_hint():
    draft = {
        "message": "You've read the CSV — what single number should each category collapse to?",
        "confidence": 0.7,
    }
    gov = governance.check(_ctx(), {"intervention": "co_reason"}, draft, {})
    assert gov["block"] is False
    assert gov["flag"] == "none"


def test_answer_seeking_sets_redirect():
    recent = [{"who": "student", "text": "just tell me the answer please"}]
    draft = {
        "message": "Let's think about what one number summarizes a category.",
        "confidence": 0.7,
    }
    gov = governance.check(_ctx(recent), {"intervention": "co_reason"}, draft, {})
    assert gov["flag"] == "redirect_answer_seeking"


def test_safe_rewrite_strips_solution_keeps_prose():
    draft = {
        "message": "ok here:\n```python\n"
        + SOLUTIONS["ds-foundations"]["source"]
        + "```\ngood luck",
        "confidence": 0.95,
        "check_question": None,
    }
    out = governance.safe_rewrite(draft, {"flag": "withholding_solution"}, EX)
    assert "groupby" not in out["message"]
    assert "good luck" in out["message"]
    assert out["confidence"] <= 0.6
    assert out["check_question"]


# --- stance-conditional blocking ---


def test_peer_stance_strips_full_solution():
    """peer: a draft containing the working solution must be blocked."""
    draft = {"message": _FULL_SOLUTION, "confidence": 0.95}
    gov = governance.check(_ctx(), {"intervention": "diagnose"}, draft, {}, stance="peer")
    assert gov["block"] is True
    assert gov["flag"] == "withholding_solution"


def test_oracle_stance_does_not_strip_full_solution():
    """oracle: the same draft must pass through unblocked."""
    draft = {"message": _FULL_SOLUTION, "confidence": 0.95}
    gov = governance.check(_ctx(), {"intervention": "diagnose"}, draft, {}, stance="oracle")
    assert gov["block"] is False
    assert gov["flag"] != "withholding_solution"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("governance: all passed")
