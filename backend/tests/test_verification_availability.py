# SPDX-License-Identifier: AGPL-3.0-only
"""A missing executable verdict cannot become a successful leak check."""

import json

import pytest

from app.agent import governance, leak_profile
from app.core import runner
from app.packs.datascience import DataSciencePack, grader


@pytest.mark.parametrize("timeout", [True, False])
def test_unavailable_execution_blocks_verifier_and_delivery(monkeypatch, timeout):
    result = runner.RunnerResult(
        False, 9, "", "", timeout, 1000, "synthetic runner unavailable", {}
    )
    monkeypatch.setattr(runner, "run_python", lambda *a, **k: result)
    pack = DataSciencePack()
    exercise = pack.get_exercise("ds-foundations")
    candidate = "```python\nprint('synthetic candidate')\n```"
    graded = grader.grade("print('synthetic candidate')", exercise)
    assert graded["pack"]["verification_unavailable"] is True
    with pytest.raises(RuntimeError, match="safety verification unavailable"):
        leak_profile.verify(
            leak_profile.build_request(candidate=candidate, exercise=exercise, stance="peer"),
            pack=pack,
        )
    with pytest.raises(RuntimeError, match="safety verification unavailable"):
        governance.check({"_exercise_full": exercise}, {}, {"message": candidate}, {}, pack=pack)


def test_executed_student_error_remains_a_student_error(monkeypatch):
    payload = {
        "ok": False,
        "goalMet": False,
        "metric": None,
        "error": "synthetic syntax error",
        "checks": [],
    }
    data = {"stdout": "", "stderr": "", "error": "synthetic syntax error", "vars": {}}
    result = runner.RunnerResult(
        True,
        0,
        "__GRADE__" + json.dumps(payload),
        "",
        False,
        1,
        None,
        {"result.json": json.dumps(data)},
    )
    monkeypatch.setattr(runner, "run_python", lambda *a, **k: result)
    pack = DataSciencePack()
    exercise = pack.get_exercise("ds-foundations")
    grade = grader.grade("synthetic invalid source", exercise)
    assert not grade.get("pack", {}).get("verification_unavailable")
    assert not pack.leak_evidence("```python\nsynthetic invalid source\n```", exercise).is_solution
