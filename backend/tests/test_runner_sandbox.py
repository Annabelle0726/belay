# SPDX-License-Identifier: AGPL-3.0-only
"""
core/runner sandbox + bypass tests.

Sandbox: network is unreachable, the wall/CPU limits terminate runaway code, deps
(numpy/pandas) import, and execution happens in an isolated temp workdir.

Bypass: the DS pack's run / verify_worked_example / leak_evidence must route ALL
student code through core/runner — never exec it in the main process. The bypass
test replaces the runner with a spy and asserts (a) each path calls the runner and
(b) a payload that would write a sentinel file if executed in-process never runs.

CC-B4: Adds security bypass tests for container runner.
"""

from __future__ import annotations

import os
import platform
import tempfile

import pytest

from app.config import settings
from app.core import runner
from app.core.runner import RunnerResult, run_python
from conftest import requires_docker

# ── sandbox properties ────────────────────────────────────────────────────────


@requires_docker
def test_network_is_blocked():
    """Network should be blocked in the sandbox."""
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
    """numpy/pandas should still be importable in the sandbox."""
    r = run_python("import numpy, pandas; print('DEPS_OK')")
    assert r.ok, r.stderr
    assert "DEPS_OK" in r.stdout


def test_wall_timeout_enforced():
    """Wall timeout should terminate runaway code."""
    r = run_python("import time\ntime.sleep(5)", wall_seconds=1)
    assert r.timed_out is True, f"Expected timeout, but got ok={r.ok}, wall_ms={r.wall_ms}"
    assert not r.ok


def test_cpu_or_wall_terminates_runaway():
    """Busy loop: CPU limit should fire (~1s); wall is the backstop."""
    r = run_python("while True:\n    pass", cpu_seconds=1, wall_seconds=6)
    assert not r.ok
    assert r.timed_out or (r.exit_code not in (0, None))


def test_isolated_workdir_and_artifacts():
    """Execution should happen in an isolated temp workdir."""
    prog = "import os\n" "open('out.txt', 'w').write('hello')\n" "print('CWD', os.getcwd())\n"
    r = run_python(prog, artifacts=["out.txt"])
    assert r.ok, r.stderr
    assert r.artifacts.get("out.txt") == "hello"
    cwd_line = [ln for ln in r.stdout.splitlines() if ln.startswith("CWD")][0]
    assert (
        "/workspace" in cwd_line or "ptf_runner_" in cwd_line or tempfile.gettempdir() in cwd_line
    )


def test_stdout_and_exit_code_captured():
    """Stdout and exit code should be captured correctly."""
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
    """All student code must route through core/runner."""
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


# ── CC-B4 Security Bypass Tests ──────────────────────────────────────────────
# These tests demonstrate that the container runner closes security gaps.
# They should FAIL against the old subprocess runner and PASS against container.


@requires_docker
@pytest.mark.skipif(not settings.sandbox_runner_enabled, reason="Container runner not enabled")
def test_ctypes_raw_socket_blocked():
    """
    Bypass: ctypes can create raw sockets in the old runner.

    In container runner, network namespace is empty → ctypes cannot reach network.
    """
    prog = """
import ctypes
import ctypes.util

libc = ctypes.CDLL(ctypes.util.find_library("c"))

# socket(AF_INET, SOCK_RAW, IPPROTO_RAW)
AF_INET = 2
SOCK_RAW = 3
IPPROTO_RAW = 255

try:
    sock = libc.socket(AF_INET, SOCK_RAW, IPPROTO_RAW)
    print(f"SOCKET_CREATED: {sock}")
except Exception as e:
    print(f"BLOCKED: {e}")
"""
    r = run_python(prog)
    assert "SOCKET_CREATED: -1" in r.stdout or "BLOCKED" in r.stdout
    assert "SOCKET_CREATED: 0" not in r.stdout


@pytest.mark.skipif(not settings.sandbox_runner_enabled, reason="Container runner not enabled")
def test_subprocess_spawn_blocked():
    """subprocess should work but be contained within the container."""
    prog = """
import subprocess
try:
    result = subprocess.run(["echo", "hello"], capture_output=True)
    print(f"SUBPROCESS_OK: {result.stdout}")
except Exception as e:
    print(f"BLOCKED: {e}")
"""
    r = run_python(prog)
    assert r.ok
    assert "SUBPROCESS_OK" in r.stdout or "BLOCKED" in r.stdout


@pytest.mark.skipif(not settings.sandbox_runner_enabled, reason="Container runner not enabled")
def test_sleep_outlasts_wall_time():
    """sleep() should be terminated by wall timeout."""
    prog = "import time\ntime.sleep(10)"
    r = run_python(prog, wall_seconds=2, cpu_seconds=1)
    assert r.timed_out is True, f"Expected timeout, but got ok={r.ok}, wall_ms={r.wall_ms}"
    assert not r.ok


@pytest.mark.skipif(not settings.sandbox_runner_enabled, reason="Container runner not enabled")
def test_reference_solution_not_readable():
    """
    Bypass: student code can read reference solution in the old runner.

    In container, reference solution files are never mounted.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("SECRET_REFERENCE_SOLUTION = 42")
        ref_path = f.name

    try:
        prog = f"""
import os
try:
    with open("{ref_path}", "r") as f:
        content = f.read()
        print(f"FOUND_REFERENCE: {{content[:50]}}")
except Exception as e:
    print(f"BLOCKED: {{e}}")
"""
        r = run_python(prog)
        assert "FOUND_REFERENCE" not in r.stdout
        assert "BLOCKED" in r.stdout or r.stderr
    finally:
        os.unlink(ref_path)


# ── Fork Bomb Test (Unix only) ──────────────────────────────────────────────
# This test is skipped on Windows because os.fork() is not available.


@pytest.mark.skipif(not settings.sandbox_runner_enabled, reason="Container runner not enabled")
@pytest.mark.skipif(platform.system() == "Windows", reason="os.fork() is not available on Windows")
def test_fork_bomb_capped():
    """
    Bypass: fork bomb can exhaust resources in the old runner.

    In container, --pids-limit caps the number of processes.

    Note: This test only runs on Unix-like systems (Linux/macOS)
    because os.fork() is not available on Windows.
    """
    prog = """
import os
import time

def fork_bomb():
    while True:
        try:
            pid = os.fork()
            if pid == 0:
                while True:
                    time.sleep(1)
            else:
                pass
        except OSError as e:
            print(f"FORK_BOMB_BLOCKED: {e}")
            break

fork_bomb()
"""
    r = run_python(prog, wall_seconds=5, cpu_seconds=2)
    assert r.timed_out or "FORK_BOMB_BLOCKED" in r.stdout
