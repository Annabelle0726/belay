"""Governance tests — the leak check is the safety-critical piece, so it gets
the most direct coverage. Stance-conditional blocking is also verified here."""
from app.agent import governance
from app.curriculum import get_exercise

BELL = get_exercise("bell")

_FULL_SOLUTION = ("here you go:\n```\nallocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all\n```")


def _ctx(message_recent=None):
    return {
        "_exercise_full": BELL,
        "recent_dialogue": message_recent or [],
        "exercise": {"concept": BELL["concept"]},
    }


def test_blocks_full_solution_in_code_block():
    draft = {"message": _FULL_SOLUTION, "confidence": 0.95}
    gov = governance.check(_ctx(), {"intervention": "diagnose"}, draft, {})
    assert gov["block"] is True
    assert gov["flag"] == "withholding_solution"


def test_blocks_bare_op_run_solution():
    draft = {"message": "just do\nallocate 2\nsuperpose q0\nentangle q0 q1", "confidence": 0.9}
    gov = governance.check(_ctx(), {"intervention": "diagnose"}, draft, {})
    assert gov["block"] is True


def test_allows_genuine_hint():
    draft = {"message": "You've got the superposition on q0. What single op would make q1 follow q0?",
             "confidence": 0.7}
    gov = governance.check(_ctx(), {"intervention": "co_reason"}, draft, {})
    assert gov["block"] is False
    assert gov["flag"] == "none"


def test_answer_seeking_sets_redirect():
    recent = [{"who": "student", "text": "just tell me the answer please"}]
    draft = {"message": "Let's think about what links the two qubits.", "confidence": 0.7}
    gov = governance.check(_ctx(recent), {"intervention": "co_reason"}, draft, {})
    assert gov["flag"] == "redirect_answer_seeking"


def test_safe_rewrite_strips_solution_keeps_prose():
    draft = {"message": "ok here:\n```\nallocate 2\nsuperpose q0\nentangle q0 q1\n```\ngood luck",
             "confidence": 0.95, "check_question": None}
    out = governance.safe_rewrite(draft, {"flag": "withholding_solution"}, BELL)
    assert "entangle q0 q1" not in out["message"]
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
