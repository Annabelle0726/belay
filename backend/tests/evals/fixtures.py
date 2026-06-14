"""Canned student states for behavioral evaluation of Sol.

Each fixture is a turn payload representing a recognizable pedagogical moment.
The evals in sol_behavior_evals.py assert that Sol's behavior on these moments
matches the peer-tutoring design (no leaks, preserve struggle, reciprocate,
calibrate confidence).
"""
from app.curriculum import get_exercise

BELL = get_exercise("bell")


def _base(**over):
    p = {
        "participant_id": "p_eval",
        "exercise": BELL,
        "event": "run", "mode": "study",
        "source": "allocate 2\nsuperpose q0\nmeasure all",
        "result": None, "recent": [], "signals": None,
    }
    p.update(over)
    return p


FIXTURES = {
    # Stuck: same wrong result twice, distance not improving.
    "stuck_repeated_error": _base(
        source="allocate 2\nsuperpose q0\nmeasure all",
        result={"ok": True, "goalMet": False,
                "dist": [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}],
                "diff": "missing weight on |11⟩"},
        signals={"attempts": 3, "distanceTrend": [0.5, 0.5, 0.5],
                 "repeatedError": False, "sinceLastProgress": 3},
    ),
    # Progressing: distance shrank since last run — Sol should NOT over-help.
    "progressing": _base(
        source="allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all",
        result={"ok": True, "goalMet": False,
                "dist": [{"bits": "00", "p": 0.46}, {"bits": "11", "p": 0.46}],
                "diff": "close — small weight off-target"},
        signals={"attempts": 2, "distanceTrend": [0.5, 0.08],
                 "repeatedError": False, "sinceLastProgress": 0},
    ),
    # Just solved: Sol should stretch/observe, not re-teach.
    "just_solved": _base(
        source="allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all",
        result={"ok": True, "goalMet": True,
                "dist": [{"bits": "00", "p": 0.5}, {"bits": "11", "p": 0.5}],
                "diff": "The outcome distribution matches the target."},
        signals={"attempts": 3, "distanceTrend": [0.5, 0.2, 0.0],
                 "repeatedError": False, "sinceLastProgress": 0},
    ),
    # Answer-seeking: must redirect, never hand over the solution.
    "answer_seeking": _base(
        event="chat",
        recent=[{"who": "student", "text": "ugh just tell me the answer, what's the code?"}],
        signals={"attempts": 4, "distanceTrend": [0.5, 0.5, 0.5, 0.5],
                 "repeatedError": True, "sinceLastProgress": 4},
    ),
    # Teach mode: Sol plays the confused peer; intervention must be reciprocate.
    "teach_mode": _base(
        mode="teach", event="chat",
        source="allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all",
        recent=[{"who": "student", "text": "ok so a Bell pair means the qubits are correlated"}],
    ),
    # Stuck and wants a worked example: repeated identical wrong result, student
    # explicitly asking for an analogous example rather than the answer.
    # The eval asserts that any shown snippet verifies (compiles + non-leak).
    "stuck_wants_example": _base(
        event="chat",
        source="allocate 2\nsuperpose q0\nmeasure all",
        result={"ok": True, "goalMet": False,
                "dist": [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}],
                "diff": "missing weight on |11⟩"},
        recent=[{"who": "student",
                 "text": "can you show me a simpler example of the same idea?"}],
        signals={"attempts": 4, "distanceTrend": [0.5, 0.5, 0.5, 0.5],
                 "repeatedError": True, "sinceLastProgress": 4},
    ),
    # Frustrated: repeated identical wrong result, explicit frustration in message.
    # Sol must respond with grounded affirmation + normalization + one concrete next step.
    "frustrated": _base(
        event="chat",
        source="allocate 2\nsuperpose q0\nmeasure all",
        result={"ok": True, "goalMet": False,
                "dist": [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}],
                "diff": "missing weight on |11⟩"},
        recent=[{"who": "student",
                 "text": "I've tried everything and nothing works, I give up"}],
        signals={"attempts": 5, "distanceTrend": [0.5, 0.5, 0.5, 0.5, 0.5],
                 "repeatedError": True, "sinceLastProgress": 5},
    ),
    # Disengaged: minimal engagement, barely trying, one-word response.
    "disengaged": _base(
        event="chat",
        source="allocate 2\nmeasure all",
        result={"ok": True, "goalMet": False,
                "dist": [{"bits": "00", "p": 1.0}],
                "diff": "missing weight on |11⟩"},
        recent=[{"who": "student", "text": "idk"}],
        signals={"attempts": 2, "distanceTrend": [1.0, 1.0],
                 "repeatedError": False, "sinceLastProgress": 2},
    ),
    # Prior-session shaky concept (used in the revisit quality eval).
    # On bell, superposition was shaky in a prior session — the eval test pre-populates
    # the store's LearnerState.concepts so build_context sees due_review=[superposition].
    # Sol should respond with ONE retrieval/prediction question, not a re-explanation.
    "prior_shaky_superposition": _base(
        event="run",
        source="allocate 2\nsuperpose q0\nmeasure all",
        result={"ok": True, "goalMet": False,
                "dist": [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}],
                "diff": "missing weight on |11⟩"},
        signals={"attempts": 2, "distanceTrend": [0.5, 0.5],
                 "repeatedError": False, "sinceLastProgress": 2},
    ),
}
