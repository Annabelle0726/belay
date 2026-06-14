"""
Spec-driven grader. Stages the exercise's declarative spec + data fixtures, runs
the student source through the `_harness` driver INSIDE core/runner (sandboxed),
and parses the harness verdict into a pack-agnostic `RunResult`.

This is the single execution path for `run`; `verify_worked_example` and the
`leak_evidence` executable oracle reuse `grade` so no student code ever runs
outside the runner.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from ...core import runner
from ...core.domain import Exercise, RunResult

_HERE = os.path.dirname(__file__)
_SPECS_DIR = os.path.join(_HERE, "specs")
_HARNESS_PATH = os.path.join(_HERE, "_harness.py")

_GRADE_PREFIX = "__GRADE__"


def spec_path(exercise_id: str) -> str:
    return os.path.join(_SPECS_DIR, f"{exercise_id}.json")


def load_spec(exercise_id: str) -> dict:
    with open(spec_path(exercise_id), "r", encoding="utf-8") as fh:
        return json.load(fh)


def has_spec(exercise_id: str) -> bool:
    return os.path.exists(spec_path(exercise_id))


def _harness_source() -> str:
    with open(_HARNESS_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _stage_data(spec: dict) -> dict:
    files = {}
    for rel in spec.get("data_files", []):
        with open(os.path.join(_SPECS_DIR, rel), "r", encoding="utf-8") as fh:
            files[rel] = fh.read()
    return files


def _parse_grade(stdout: str) -> Optional[dict]:
    for line in stdout.splitlines():
        if line.startswith(_GRADE_PREFIX):
            try:
                return json.loads(line[len(_GRADE_PREFIX):])
            except json.JSONDecodeError:
                return None
    return None


def _summary(grade: dict) -> str:
    if grade.get("error"):
        return f"error: {grade['error']}"
    checks = grade.get("checks", [])
    n_pass = sum(1 for c in checks if c.get("ok"))
    parts = [f"{n_pass}/{len(checks)} checks passed"]
    for c in checks:
        mark = "ok" if c.get("ok") else "FAIL"
        detail = f" ({c['detail']})" if c.get("detail") else ""
        parts.append(f"{c['type']}: {mark}{detail}")
    return "; ".join(parts)


def grade(source: str, exercise: Exercise) -> RunResult:
    """Grade ``source`` against ``exercise``'s spec inside the sandbox runner."""
    ex_id = exercise.get("id", "")
    spec = load_spec(ex_id)
    files = _stage_data(spec)
    files["student.py"] = source
    files["spec.json"] = json.dumps(spec)

    res = runner.run_python(_harness_source(), files=files)
    grade_obj = _parse_grade(res.stdout)

    if grade_obj is None:
        # Harness produced no verdict: crash, timeout, or resource kill.
        err = (res.error
               or (res.stderr.strip()[-300:] if res.stderr.strip() else None)
               or "grader produced no verdict")
        return {
            "ok": False, "goalMet": False, "metric": None, "error": err,
            "pack": {"id": "datascience", "checks": [], "stdout": res.stdout[-500:],
                     "summary": err, "timed_out": res.timed_out},
        }

    return {
        "ok": bool(grade_obj.get("ok")),
        "goalMet": bool(grade_obj.get("goalMet")),
        "metric": grade_obj.get("metric"),
        "error": grade_obj.get("error"),
        "pack": {
            "id": "datascience",
            "checks": grade_obj.get("checks", []),
            "stdout": grade_obj.get("stdout", ""),
            "summary": _summary(grade_obj),
        },
    }
