"""Parity tests for the quantum grader — the same cases that validated the
artifact, now run against the backend's LocalSimulator + grader."""
from app.curriculum import get_exercise
from app.quantum import LocalSimulator, compile_and_run

SIM = LocalSimulator()

SOLUTIONS = {
    "superpose": "allocate 1\nsuperpose q0\nmeasure all",
    "flip": "allocate 1\nflip q0\nmeasure all",
    "bell": "allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all",
    "uniform2": "allocate 2\nsuperpose q0\nsuperpose q1\nmeasure all",
    "ghz": "allocate 3\nsuperpose q0\nentangle q0 q1\nentangle q1 q2\nmeasure all",
    "phasekick": "allocate 1\nsuperpose q0\nphase q0\nmeasure all",
}


def _run(ex_id, src):
    ex = get_exercise(ex_id)
    return compile_and_run(src, ex["target"], ex["tol"], SIM)


def test_canonical_solutions_meet_goal():
    for ex_id, src in SOLUTIONS.items():
        res = _run(ex_id, src)
        assert res["ok"], f"{ex_id}: {res.get('error')}"
        assert res["goalMet"] is True, f"{ex_id} did not meet goal: {res['diff']}"
        assert res["tvd"] < 1e-6, f"{ex_id} tvd={res['tvd']}"


def test_superpose_only_fails_bell():
    res = _run("bell", "allocate 2\nsuperpose q0\nmeasure all")
    assert res["ok"] and res["goalMet"] is False
    assert "10" in res["diff"] or "01" in res["diff"]


def test_two_qubit_attempt_fails_ghz():
    res = _run("ghz", "allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all")
    assert res["ok"] and res["goalMet"] is False


def test_error_op_before_allocate():
    res = _run("superpose", "superpose q0\nmeasure all")
    assert res["ok"] is False and "Allocate" in res["error"]


def test_error_qubit_out_of_range():
    res = _run("superpose", "allocate 1\nsuperpose q1\nmeasure all")
    assert res["ok"] is False and "bad qubit" in res["error"]


def test_error_unknown_op():
    res = _run("superpose", "allocate 1\nfoobar q0\nmeasure all")
    assert res["ok"] is False and "Unknown operation" in res["error"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("quantum parity: all passed")
