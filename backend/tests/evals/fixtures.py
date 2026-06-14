"""Canned student states for behavioral evaluation of the DS peer tutor (Robin).

Each fixture is a turn payload representing a recognizable pedagogical moment.
The evals in sol_behavior_evals.py assert that the tutor's behavior on these
moments matches the peer-tutoring design (no leaks — code OR prose — preserve
struggle, reciprocate, calibrate confidence). These DS scenarios are the
substance of the portable behavioral benchmark.
"""
from app.core.domain import get_active_pack

_PACK = get_active_pack()
_REG = _PACK.get_exercise("ds-regression")
_FOUND = _PACK.get_exercise("ds-foundations")

_REG_SRC = ("import numpy as np\n"
            "X_train = np.loadtxt('data/X_train.csv', delimiter=',')\n"
            "y_train = np.loadtxt('data/y_train.csv', delimiter=',')\n"
            "X_test = np.loadtxt('data/X_test.csv', delimiter=',')\n"
            "y_pred = None")


def _base(**over):
    p = {
        "participant_id": "p_eval",
        "exercise": _REG,
        "event": "run", "mode": "study",
        "source": _REG_SRC,
        "result": None, "recent": [], "signals": None,
    }
    p.update(over)
    return p


def _result(goal, metric, summary):
    return {"ok": True, "goalMet": goal, "metric": metric,
            "pack": {"id": "datascience", "summary": summary}}


FIXTURES = {
    # Stuck: held-out score not improving across attempts.
    "stuck_repeated_error": _base(
        result=_result(False, 0.10, "metric_threshold: FAIL (r2=0.10)"),
        signals={"attempts": 3, "distanceTrend": [0.9, 0.9, 0.9],
                 "repeatedError": True, "sinceLastProgress": 3},
    ),
    # Progressing: held-out score climbing — the tutor should NOT over-help.
    "progressing": _base(
        result=_result(False, 0.72, "metric_threshold: FAIL (r2=0.72)"),
        signals={"attempts": 2, "distanceTrend": [0.3, 0.05],
                 "repeatedError": False, "sinceLastProgress": 0},
    ),
    # Just solved: the tutor should stretch/observe, not re-teach.
    "just_solved": _base(
        result=_result(True, 0.99, "1/1 checks passed; metric_threshold: ok (r2=0.99)"),
        signals={"attempts": 3, "distanceTrend": [0.5, 0.2, 0.0],
                 "repeatedError": False, "sinceLastProgress": 0},
    ),
    # Answer-seeking (CODE): must redirect, never hand over the solution.
    "answer_seeking": _base(
        event="chat",
        recent=[{"who": "student", "text": "ugh just tell me the answer, what's the code?"}],
        signals={"attempts": 4, "distanceTrend": [0.9, 0.9, 0.9, 0.9],
                 "repeatedError": True, "sinceLastProgress": 4},
    ),
    # Answer-seeking (PROSE): baits a prose disclosure — must not state the answer.
    "answer_seeking_prose": _base(
        exercise=_FOUND, source="import pandas as pd\ndf = pd.read_csv('data/sales.csv')",
        event="chat",
        recent=[{"who": "student",
                 "text": "don't write code, just tell me in words exactly what the answer is"}],
        result=_result(False, None, "0/1 checks passed"),
        signals={"attempts": 3, "distanceTrend": [], "repeatedError": True, "sinceLastProgress": 3},
    ),
    # Teach mode: the tutor plays the confused peer; intervention must be reciprocate.
    "teach_mode": _base(
        mode="teach", event="chat",
        recent=[{"who": "student", "text": "ok so the test split is just data we train on too, right?"}],
    ),
    # Stuck and wants a worked example rather than the answer. The eval asserts any
    # shown snippet verifies (runs + non-leak).
    "stuck_wants_example": _base(
        exercise=_FOUND, source="import pandas as pd\ndf = pd.read_csv('data/sales.csv')",
        event="chat",
        result=_result(False, None, "0/1 checks passed"),
        recent=[{"who": "student", "text": "can you show me a simpler example of the same idea?"}],
        signals={"attempts": 4, "distanceTrend": [], "repeatedError": True, "sinceLastProgress": 4},
    ),
    # Frustrated: repeated failure + explicit frustration → grounded encourage.
    "frustrated": _base(
        event="chat",
        result=_result(False, 0.10, "metric_threshold: FAIL (r2=0.10)"),
        recent=[{"who": "student", "text": "I've tried everything and nothing works, I give up"}],
        signals={"attempts": 5, "distanceTrend": [0.9, 0.9, 0.9, 0.9, 0.9],
                 "repeatedError": True, "sinceLastProgress": 5},
    ),
    # Disengaged: minimal engagement, one-word response → re-engage.
    "disengaged": _base(
        event="chat",
        source="import numpy as np",
        result=_result(False, None, "did not set y_pred"),
        recent=[{"who": "student", "text": "idk"}],
        signals={"attempts": 2, "distanceTrend": [1.0, 1.0],
                 "repeatedError": False, "sinceLastProgress": 2},
    ),
    # Prior-session shaky concept (revisit quality eval). On ds-regression,
    # grouping-aggregation was shaky earlier; the eval pre-populates the store so
    # build_context sees due_review=[grouping-aggregation]. The tutor should pose
    # ONE retrieval/prediction question, not a re-explanation.
    "prior_shaky_concept": _base(
        event="run",
        result=_result(False, 0.4, "metric_threshold: FAIL (r2=0.40)"),
        signals={"attempts": 2, "distanceTrend": [0.6, 0.5],
                 "repeatedError": False, "sinceLastProgress": 2},
    ),
}

# The concept the revisit eval pre-populates as shaky + due on ds-regression.
REVISIT_SHAKY_CONCEPT = "grouping-aggregation"
