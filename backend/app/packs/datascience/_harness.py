"""
Grading harness — executed INSIDE core/runner (the sandbox), never in-process.

Reads ``spec.json`` and ``student.py`` from the (isolated) working directory,
executes the student source with stdout captured, evaluates the spec's checks,
and prints a single ``__GRADE__<json>`` line on real stdout. The pack parses that
line back into a `RunResult`.

Declarative check types (convergent with Quad pkg/gradingspec — see GRADING_SPEC.md):
  stdout_contains | stdout_equals | var_numeric | var_dataframe |
  function_contract | metric_threshold | var_threshold
"""
import contextlib
import io
import json

import numpy as np


def _load(name):
    with open(name, encoding="utf-8") as fh:
        return fh.read()


def _metric(name, y_true, y_pred):
    yt = np.asarray(y_true, dtype=float).ravel()
    yp = np.asarray(y_pred, dtype=float).ravel()
    if yt.shape != yp.shape:
        raise ValueError(f"shape mismatch: truth {yt.shape} vs pred {yp.shape}")
    if name == "r2":
        ss_res = float(((yt - yp) ** 2).sum())
        ss_tot = float(((yt - yt.mean()) ** 2).sum())
        return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    if name == "mse":
        return float(((yt - yp) ** 2).mean())
    if name == "mae":
        return float(np.abs(yt - yp).mean())
    if name == "accuracy":
        return float((yt == yp).mean())
    raise ValueError(f"unknown metric {name!r}")


def _cmp(value, op, threshold):
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == "==":
        return value == threshold
    raise ValueError(f"unknown op {op!r}")


def _run_check(chk, ns, stdout_text):
    """Return (ok: bool, primary_metric: float|None, detail: str)."""
    t = chk["type"]
    if t == "stdout_contains":
        return (chk["text"] in stdout_text), None, ""
    if t == "stdout_equals":
        return (stdout_text.strip() == chk["text"].strip()), None, ""
    if t == "var_numeric":
        val = ns.get(chk["var"])
        exp = chk["expected"]
        tol = float(chk.get("tol", 1e-6))
        if isinstance(exp, dict):
            ok = val is not None and all(
                abs(float(val[k]) - float(v)) <= tol for k, v in exp.items()
            )
        else:
            ok = val is not None and abs(float(val) - float(exp)) <= tol
        return ok, None, ""
    if t == "var_dataframe":
        import pandas as pd
        val = ns.get(chk["var"])
        exp = pd.DataFrame(chk["expected"])
        tol = float(chk.get("tol", 1e-6))
        try:
            pd.testing.assert_frame_equal(
                val.reset_index(drop=True), exp.reset_index(drop=True),
                check_dtype=False, atol=tol, check_like=True,
            )
            return True, None, ""
        except Exception as exc:  # noqa: BLE001
            return False, None, str(exc)[:120]
    if t == "function_contract":
        fn = ns.get(chk["func"])
        if not callable(fn):
            return False, None, f"{chk['func']} is not callable"
        tol = float(chk.get("tol", 1e-6))
        for case in chk["cases"]:
            got = fn(*case.get("args", []))
            exp = case["expected"]
            if abs(float(got) - float(exp)) > tol:
                return False, None, f"case {case.get('args')}: got {got}, want {exp}"
        return True, None, ""
    if t == "metric_threshold":
        pred = ns.get(chk["pred_var"])
        truth = np.loadtxt(chk["truth_file"], delimiter=",")
        m = _metric(chk["metric"], truth, pred)
        ok = _cmp(m, chk.get("op", ">="), float(chk["threshold"]))
        return ok, (m if chk.get("primary") else None), f"{chk['metric']}={m:.4f}"
    if t == "var_threshold":
        val = float(ns.get(chk["var"]))
        ok = _cmp(val, chk.get("op", "<="), float(chk["threshold"]))
        return ok, (val if chk.get("primary") else None), f"{chk['var']}={val:.4f}"
    raise ValueError(f"unknown check type {t!r}")


def main():
    spec = json.loads(_load("spec.json"))
    student_src = _load("student.py")

    ns = {"__name__": "__student__"}
    buf = io.StringIO()
    err = None
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(student_src, "<student>", "exec"), ns)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    stdout_text = buf.getvalue()

    checks_out = []
    metric_value = None
    goal = err is None
    if err is None:
        for chk in spec.get("checks", []):
            try:
                ok, primary, detail = _run_check(chk, ns, stdout_text)
            except Exception as exc:  # noqa: BLE001
                ok, primary, detail = False, None, f"{type(exc).__name__}: {exc}"
            if primary is not None:
                metric_value = primary
            checks_out.append({"type": chk["type"], "ok": bool(ok), "detail": detail})
            goal = goal and bool(ok)

    print("__GRADE__" + json.dumps({
        "ok": err is None,
        "error": err,
        "goalMet": bool(goal),
        "metric": metric_value,
        "checks": checks_out,
        "stdout": stdout_text[-2000:],
    }))


if __name__ == "__main__":
    main()
