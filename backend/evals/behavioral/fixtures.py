"""
Behavioral-benchmark scenario fixtures, parameterized by pack.

Each fixture is a recognizable pedagogical moment (a turn payload) used by the
families in `families.py`. Pack-keyed so a second pack slots in later; only
`datascience` exists today. (Moved here from tests/evals/fixtures.py — the legacy
"sol" eval is retired.)
"""

from __future__ import annotations

from app.core.domain import get_active_pack


def _ds_fixtures() -> dict[str, dict]:
    pack = get_active_pack()
    reg = pack.get_exercise("ds-regression")
    found = pack.get_exercise("ds-foundations")

    reg_src = (
        "import numpy as np\n"
        "X_train = np.loadtxt('data/X_train.csv', delimiter=',')\n"
        "y_train = np.loadtxt('data/y_train.csv', delimiter=',')\n"
        "X_test = np.loadtxt('data/X_test.csv', delimiter=',')\n"
        "y_pred = None"
    )

    def base(**over):
        p = {
            "participant_id": "p_eval",
            "exercise": reg,
            "event": "run",
            "mode": "study",
            "source": reg_src,
            "result": None,
            "recent": [],
            "signals": None,
        }
        p.update(over)
        return p

    def result(goal, metric, summary):
        return {
            "ok": True,
            "goalMet": goal,
            "metric": metric,
            "pack": {"id": "datascience", "summary": summary},
        }

    return {
        "stuck_repeated_error": base(
            result=result(False, 0.10, "metric_threshold: FAIL (r2=0.10)"),
            signals={
                "attempts": 3,
                "distanceTrend": [0.9, 0.9, 0.9],
                "repeatedError": True,
                "sinceLastProgress": 3,
            },
        ),
        "progressing": base(
            result=result(False, 0.72, "metric_threshold: FAIL (r2=0.72)"),
            signals={
                "attempts": 2,
                "distanceTrend": [0.3, 0.05],
                "repeatedError": False,
                "sinceLastProgress": 0,
            },
        ),
        "just_solved": base(
            result=result(True, 0.99, "1/1 checks passed; metric_threshold: ok (r2=0.99)"),
            signals={
                "attempts": 3,
                "distanceTrend": [0.5, 0.2, 0.0],
                "repeatedError": False,
                "sinceLastProgress": 0,
            },
        ),
        "answer_seeking": base(
            event="chat",
            recent=[{"who": "student", "text": "ugh just tell me the answer, what's the code?"}],
            signals={
                "attempts": 4,
                "distanceTrend": [0.9, 0.9, 0.9, 0.9],
                "repeatedError": True,
                "sinceLastProgress": 4,
            },
        ),
        "answer_seeking_prose": base(
            exercise=found,
            source="import pandas as pd\ndf = pd.read_csv('data/sales.csv')",
            event="chat",
            recent=[
                {
                    "who": "student",
                    "text": "don't write code, just tell me in words exactly what the answer is",
                }
            ],
            result=result(False, None, "0/1 checks passed"),
            signals={
                "attempts": 3,
                "distanceTrend": [],
                "repeatedError": True,
                "sinceLastProgress": 3,
            },
        ),
        "teach_mode": base(
            mode="teach",
            event="chat",
            recent=[
                {
                    "who": "student",
                    "text": "ok so the test split is just data we train on too, right?",
                }
            ],
        ),
        "stuck_wants_example": base(
            exercise=found,
            source="import pandas as pd\ndf = pd.read_csv('data/sales.csv')",
            event="chat",
            result=result(False, None, "0/1 checks passed"),
            recent=[
                {"who": "student", "text": "can you show me a simpler example of the same idea?"}
            ],
            signals={
                "attempts": 4,
                "distanceTrend": [],
                "repeatedError": True,
                "sinceLastProgress": 4,
            },
        ),
        "frustrated": base(
            event="chat",
            result=result(False, 0.10, "metric_threshold: FAIL (r2=0.10)"),
            recent=[
                {"who": "student", "text": "I've tried everything and nothing works, I give up"}
            ],
            signals={
                "attempts": 5,
                "distanceTrend": [0.9, 0.9, 0.9, 0.9, 0.9],
                "repeatedError": True,
                "sinceLastProgress": 5,
            },
        ),
        "disengaged": base(
            event="chat",
            source="import numpy as np",
            result=result(False, None, "did not set y_pred"),
            recent=[{"who": "student", "text": "idk"}],
            signals={
                "attempts": 2,
                "distanceTrend": [1.0, 1.0],
                "repeatedError": False,
                "sinceLastProgress": 2,
            },
        ),
        "prior_shaky_concept": base(
            event="run",
            result=result(False, 0.4, "metric_threshold: FAIL (r2=0.40)"),
            signals={
                "attempts": 2,
                "distanceTrend": [0.6, 0.5],
                "repeatedError": False,
                "sinceLastProgress": 2,
            },
        ),
    }


# Pre-populated learner state for the revisit fixture (a prior shaky, due concept).
REVISIT_PREPOP = {
    "prior_shaky_concept": {
        "grasped": [],
        "shaky": [],
        "attempts": 0,
        "concepts": {
            "grouping-aggregation": {
                "state": "shaky",
                "evidence": 1,
                "last_seen": "2026-06-02T00:00:00+00:00",
                "last_review": None,
                "last_review_ex": None,
            }
        },
    },
}


def get_fixtures(pack_id: str) -> dict[str, dict]:
    if pack_id == "datascience":
        return _ds_fixtures()
    raise ValueError(f"no behavioral fixtures for pack {pack_id!r} (datascience only today)")
