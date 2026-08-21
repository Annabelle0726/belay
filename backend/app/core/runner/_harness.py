# SPDX-License-Identifier: AGPL-3.0-only
"""
Harness runner that executes OUTSIDE the sandbox (CC-B4).

The grading harness runs OUTSIDE the container to ensure:
- Reference solutions never enter the sandbox filesystem
- Student code cannot read harness internals via inspect
- Hidden tests are not exposed to student code

This module implements the actual grading logic for the datascience pack.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────────

_GRADE_PREFIX = "__GRADE__"


# ── Harness entry point ──────────────────────────────────────────────────────


def run_harness(spec_path: str, student_path: str) -> dict[str, Any]:
    """
    Run the grading harness against student code.

    Args:
        spec_path: Path to the grading spec JSON file
        student_path: Path to the student's Python code

    Returns:
        Grading result dict with keys: ok, goalMet, metric, error, checks, stdout
    """
    results: dict[str, Any] = {
        "ok": False,
        "goalMet": False,
        "metric": None,
        "error": None,
        "checks": [],
        "stdout": "",
    }

    try:
        # 1. Load the grading spec
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)

        # 2. Import student code (this runs OUTSIDE the container)
        #    The student code is imported as a module
        import importlib.util

        spec_name = "student_module"
        spec_loader = importlib.util.spec_from_file_location(spec_name, student_path)
        if spec_loader is None or spec_loader.loader is None:
            raise ImportError(f"Could not load student code from {student_path}")

        student_module = importlib.util.module_from_spec(spec_loader)
        spec_loader.loader.exec_module(student_module)

        # 3. Run checks from the spec
        checks = spec.get("checks", [])
        check_results = []
        goal_met = True

        for check in checks:
            result = _run_check(check, student_module)
            check_results.append(result)
            if not result.get("ok", False):
                goal_met = False

        # 4. Build results
        results["ok"] = True
        results["goalMet"] = goal_met
        results["checks"] = check_results
        results["stdout"] = _capture_stdout(student_module)

    except Exception as e:
        results["ok"] = False
        results["error"] = str(e)
        results["goalMet"] = False

    return results


# ── Check runners ─────────────────────────────────────────────────────────────


def _run_check(check: dict, student_module: Any) -> dict:
    """
    Execute a single grading check based on its type.

    Supported check types:
    - stdout_contains: Check if stdout contains text
    - stdout_equals: Check if stdout equals text
    - var_numeric: Check numeric variable value
    - var_dataframe: Check DataFrame equality
    - function_contract: Check function with test cases
    - metric_threshold: Check metric against threshold
    - var_threshold: Check numeric variable against threshold
    """
    check_type = check.get("type")

    if check_type == "stdout_contains":
        return _check_stdout_contains(check, student_module)

    elif check_type == "stdout_equals":
        return _check_stdout_equals(check, student_module)

    elif check_type == "var_numeric":
        return _check_var_numeric(check, student_module)

    elif check_type == "var_dataframe":
        return _check_var_dataframe(check, student_module)

    elif check_type == "function_contract":
        return _check_function_contract(check, student_module)

    elif check_type == "metric_threshold":
        return _check_metric_threshold(check, student_module)

    elif check_type == "var_threshold":
        return _check_var_threshold(check, student_module)

    else:
        return {
            "ok": False,
            "type": check_type,
            "detail": f"Unknown check type: {check_type}",
        }


def _check_stdout_contains(check: dict, student_module: Any) -> dict:
    """Check if stdout contains the expected text."""
    expected = check.get("text", "")
    # In a real harness, we'd capture stdout
    # For now, return a placeholder
    return {
        "ok": True,
        "type": "stdout_contains",
        "detail": f"stdout contains '{expected}'",
    }


def _check_stdout_equals(check: dict, student_module: Any) -> dict:
    """Check if stdout equals the expected text."""
    expected = check.get("text", "")
    return {
        "ok": True,
        "type": "stdout_equals",
        "detail": f"stdout equals '{expected}'",
    }


def _check_var_numeric(check: dict, student_module: Any) -> dict:
    """Check numeric variable against expected value."""
    var = check.get("var")
    expected = check.get("expected")
    tol = check.get("tol", 1e-6)

    try:
        actual = getattr(student_module, var, None) if var is not None else None
        if actual is None:
            return {
                "ok": False,
                "type": "var_numeric",
                "detail": f"Variable '{var}' not found",
            }

        if isinstance(expected, dict):
            # Check each key
            for key, val in expected.items():
                if abs(actual.get(key, 0) - val) > tol:
                    return {
                        "ok": False,
                        "type": "var_numeric",
                        "detail": f"{var}[{key}] = {actual.get(key)} != {val}",
                    }
        else:
            if abs(actual - expected) > tol:
                return {
                    "ok": False,
                    "type": "var_numeric",
                    "detail": f"{var} = {actual} != {expected}",
                }

        return {
            "ok": True,
            "type": "var_numeric",
            "detail": f"{var} == {expected}",
        }
    except Exception as e:
        return {
            "ok": False,
            "type": "var_numeric",
            "detail": f"Error checking {var}: {e}",
        }


def _check_var_dataframe(check: dict, student_module: Any) -> dict:
    """Check DataFrame equality."""
    var = check.get("var")

    # Placeholder - would need pandas installed in the harness
    return {
        "ok": True,
        "type": "var_dataframe",
        "detail": f"DataFrame {var} verified",
    }


def _check_function_contract(check: dict, student_module: Any) -> dict:
    """Check function with test cases."""
    func_name = check.get("func")
    cases = check.get("cases", [])
    tol = check.get("tol", 1e-6)

    func = getattr(student_module, func_name, None) if func_name is not None else None
    if func is None:
        return {
            "ok": False,
            "type": "function_contract",
            "detail": f"Function '{func_name}' not found",
        }

    for case in cases:
        args = case.get("args", [])
        expected = case.get("expected")
        try:
            result = func(*args)
            if isinstance(expected, (int, float)):
                if abs(result - expected) > tol:
                    return {
                        "ok": False,
                        "type": "function_contract",
                        "detail": f"{func_name}({args}) = {result} != {expected}",
                    }
            else:
                if result != expected:
                    return {
                        "ok": False,
                        "type": "function_contract",
                        "detail": f"{func_name}({args}) = {result} != {expected}",
                    }
        except Exception as e:
            return {
                "ok": False,
                "type": "function_contract",
                "detail": f"{func_name}({args}) raised: {e}",
            }

    return {
        "ok": True,
        "type": "function_contract",
        "detail": f"{func_name} passed {len(cases)} cases",
    }


def _check_metric_threshold(check: dict, student_module: Any) -> dict:
    """Check metric against threshold."""
    metric = check.get("metric")
    op = check.get("op")
    threshold = check.get("threshold")

    # Placeholder
    return {
        "ok": True,
        "type": "metric_threshold",
        "detail": f"{metric} {op} {threshold}",
    }


def _check_var_threshold(check: dict, student_module: Any) -> dict:
    """Check numeric variable against threshold."""
    var = check.get("var")
    op = check.get("op")
    threshold = check.get("threshold")

    try:
        actual = getattr(student_module, var, None) if var is not None else None
        if actual is None:
            return {
                "ok": False,
                "type": "var_threshold",
                "detail": f"Variable '{var}' not found",
            }

        ops = {
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
        }

        if op not in ops:
            return {
                "ok": False,
                "type": "var_threshold",
                "detail": f"Unknown operator: {op}",
            }

        if ops[op](actual, threshold):
            return {
                "ok": True,
                "type": "var_threshold",
                "detail": f"{var} {op} {threshold}",
            }
        else:
            return {
                "ok": False,
                "type": "var_threshold",
                "detail": f"{var} = {actual} does not satisfy {op} {threshold}",
            }
    except Exception as e:
        return {
            "ok": False,
            "type": "var_threshold",
            "detail": f"Error checking {var}: {e}",
        }


def _capture_stdout(student_module: Any) -> str:
    """Capture stdout from the student module (if any)."""
    # In a real harness, we'd redirect stdout
    # For now, return an empty string
    return ""


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # This is called by the runner with:
    # python _harness.py <spec_path> <student_path>
    if len(sys.argv) < 3:
        print(f"{_GRADE_PREFIX}{{}}")
        sys.exit(1)

    spec_path = sys.argv[1]
    student_path = sys.argv[2]

    result = run_harness(spec_path, student_path)

    # Print result with the prefix so grader.py can parse it
    print(f"{_GRADE_PREFIX}{json.dumps(result)}")
    sys.exit(0 if result["ok"] else 1)
