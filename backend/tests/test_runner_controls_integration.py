# SPDX-License-Identifier: AGPL-3.0-only
"""Contracts lost when host grading and shared controls are combined."""

import pytest

from app.core import runner
from app.core.runner._harness import _validate_result
from app.packs.datascience import DataSciencePack


@pytest.mark.parametrize(
    "source,line,error",
    [
        ("print('before error')\nraise ValueError('synthetic failure')", 2, "ValueError"),
        ("def broken(", 1, "SyntaxError"),
    ],
)
def test_container_student_error_preserves_feedback_location(source, line, error):
    pack = DataSciencePack()
    result = pack.run(source, pack.get_exercise("ds-foundations"))
    assert result["ok"] is False
    assert result["pack"]["execution_status"] == "student_error"
    assert result["pack"]["error_line"] == line
    assert result["pack"]["verification_unavailable"] is False
    assert error in result["error"]


@pytest.mark.parametrize("timed_out,status", [(True, "timeout"), (False, "infrastructure_error")])
def test_missing_container_result_preserves_execution_status(monkeypatch, timed_out, status):
    monkeypatch.setattr(
        runner,
        "run_python",
        lambda *a, **k: runner.RunnerResult(False, 9, "", "", timed_out, 10, "synthetic failure"),
    )
    pack = DataSciencePack()
    result = pack.run("pass", pack.get_exercise("ds-foundations"))
    assert result["pack"]["execution_status"] == status
    assert result["pack"]["timed_out"] is timed_out
    assert result["pack"]["verification_unavailable"] is True


@pytest.mark.parametrize("line", [True, 0, -1, 1.5, "1"])
def test_structured_error_location_rejects_invalid_values(line):
    with pytest.raises(ValueError):
        _validate_result(
            {"stdout": "", "stderr": "", "error": "synthetic", "vars": {}, "error_line": line}
        )
