# SPDX-License-Identifier: AGPL-3.0-only
"""
Helper functions for adversarial leak testing.
"""

from __future__ import annotations

from app.core.registry import get_active_pack


def _payload(pid, student_text=None, stance="peer", exercise_id="ds-foundations"):
    """
    Helper to create payload for run_turn tests.

    This constructs a complete payload dict that can be passed to run_turn().
    Used by Attack.run() to simulate student messages.
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


# 如果其他地方也需要，可以导出
__all__ = ["_payload"]
