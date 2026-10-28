# SPDX-License-Identifier: AGPL-3.0-only
from app.core.registry import get_active_pack


def _payload(pid, student_text=None, stance="peer", exercise_id="ds-foundations"):
    """
    Create a payload dict for run_turn() tests.

    This helper constructs the full payload required by the tutor loop.
    It is shared across test_distress.py, test_injection_guard.py, and adversarial tests.
    """
    pack = get_active_pack()
    exercise = pack.get_exercise(exercise_id)

    recent = [{"who": "student", "text": student_text}] if student_text else []
    return {
        "participant_id": pid,
        "exercise": exercise,
        "event": "chat",
        "mode": "study",
        "stance": stance,
        "source": "import pandas as pd",
        "result": {
            "ok": True,
            "goalMet": False,
            "metric": None,
            "pack": {"id": pack.id, "summary": "0/1 checks passed"},
        },
        "recent": recent,
        "signals": None,
    }
