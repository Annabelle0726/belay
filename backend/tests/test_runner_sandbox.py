"""
core/runner sandbox + bypass tests.

Sandbox: network is unreachable, the wall/CPU limits terminate runaway code, deps
(numpy/pandas) import, and execution happens in an isolated temp workdir.

Bypass: the DS pack's run / verify_worked_example / leak_evidence must route ALL
student code through core/runner — never exec it in the main process. The bypass
test replaces the runner with a spy and asserts (a) each path calls the runner and
(b) a payload that would write a sentinel file if executed in-process never runs.
"""

from __future__ import annotations

import os
import tempfile

from app.core import runner
from app.core.runner import RunnerResult, run_python

# ── sandbox properties ────────────────────────────────────────────────────────


def test_network_is_blocked():
    prog = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('8.8.8.8', 53), timeout=2)\n"
        "    print('NET_OK')\n"
        "except OSError:\n"
        "    print('BLOCKED')\n"
    )
    r = run_python(prog)
    assert r.ok
    assert "BLOCKED" in r.stdout
    assert "NET_OK" not in r.stdout


def test_pack_deps_still_importable():
    r = run_python("import numpy, pandas; print('DEPS_OK')")
    assert r.ok, r.stderr
    assert "DEPS_OK" in r.stdout


def test_wall_timeout_enforced():
    r = run_python("import time\ntime.sleep(5)", wall_seconds=1)
    assert r.timed_out is True
    assert not r.ok
    assert "timeout" in (r.error or "")


def test_cpu_or_wall_terminates_runaway():
    # Busy loop: CPU limit should fire (~1s); wall is the backstop.
    r = run_python("while True:\n    pass", cpu_seconds=1, wall_seconds=6)
    assert not r.ok
    assert r.timed_out or (r.exit_code not in (0, None))


def test_isolated_workdir_and_artifacts():
    prog = (
        "import os\n"
        "open('out.txt', 'w').write('hello')\n"
        "print('CWD', os.getcwd())\n"
        "print('HOME', os.environ.get('HOME'))\n"
    )
    r = run_python(prog, artifacts=["out.txt"])
    assert r.ok, r.stderr
    assert r.artifacts.get("out.txt") == "hello"
    # cwd and HOME are the isolated temp workdir
    cwd_line = [ln for ln in r.stdout.splitlines() if ln.startswith("CWD")][0]
    assert tempfile.gettempdir() in cwd_line or "ptf_runner_" in cwd_line


def test_stdout_and_exit_code_captured():
    r = run_python("print('hi'); raise SystemExit(3)")
    assert "hi" in r.stdout
    assert r.exit_code == 3
    assert not r.ok


# ── bypass: pack student-code paths must use the runner ───────────────────────

_CANNED = RunnerResult(
    ok=True,
    exit_code=0,
    stdout='__GRADE__{"ok": true, "goalMet": false, "metric": null, "checks": [], "stdout": ""}',
    stderr="",
    timed_out=False,
    wall_ms=1.0,
    error=None,
    artifacts={},
)


def test_student_code_never_runs_outside_the_runner(monkeypatch):
    from app.packs.datascience import DataSciencePack

    calls = {"n": 0}

    def _spy(program, **kwargs):
        calls["n"] += 1
        return _CANNED

    # Patch the runner entrypoint the grader calls.
    monkeypatch.setattr(runner, "run_python", _spy)

    marker = os.path.join(tempfile.mkdtemp(prefix="ptf_bypass_"), "MARKER")
    # If this payload is ever exec'd in-process, the marker file appears.
    payload = f"open({marker!r}, 'w').write('executed in-process')\nresult = {{}}\n"

    pack = DataSciencePack()
    ex = pack.get_exercise("ds-foundations")

    pack.run(payload, ex)
    pack.verify_worked_example({"source": payload}, ex)
    pack.leak_evidence("```python\n" + payload + "\n```", ex)

    # Each path routed student code through the runner (the spy).
    assert calls["n"] >= 3
    # And nothing executed it in-process.
    assert not os.path.exists(marker), "student code executed outside the runner!"
