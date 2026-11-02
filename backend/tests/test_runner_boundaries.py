# SPDX-License-Identifier: AGPL-3.0-only
import json
import subprocess
import sys
import time

import pytest

from app.core.runner import _sandbox, run_python
from app.core.runner._bounded import capture
from app.core.runner._harness import _validate_result
from app.core.runner._utils import prepare_workdir


@pytest.mark.parametrize("channel", [1, 2])
def test_pipe_flood_bounded_while_reading(channel):
    start = time.monotonic()
    outcome = capture(
        [sys.executable, "-c", f"import os\nwhile True: os.write({channel},b'x'*8192)"],
        limit=32768,
        timeout=5,
    )
    assert outcome["overflow"]
    assert len(outcome["stdout"]) + len(outcome["stderr"]) <= 32768
    assert time.monotonic() - start < 8


def test_one_extra_byte_triggers_overflow_before_wall_timeout():
    outcome = capture(
        [sys.executable, "-c", "import os,time; os.write(1,b'x'*32769); time.sleep(30)"],
        limit=32768,
        timeout=2,
    )
    assert outcome["stdout"] == b"x" * 32768
    assert outcome["overflow"] and not outcome["timed_out"]


@pytest.mark.parametrize("cleanup_state", ["already_removed", "still_present", "daemon_down"])
def test_cleanup_requires_confirmed_removal(monkeypatch, cleanup_state):
    envelope = {
        "exit_code": 0,
        "timed_out": False,
        "error": None,
        "stdout": "done",
        "stderr": "",
        "artifacts": {},
    }
    container_name = None

    def successful_capture(command, **kwargs):
        assert container_name and command == ["docker", "start", "--attach", container_name]
        return {
            "stdout": json.dumps(envelope).encode(),
            "stderr": b"",
            "exit_code": 0,
            "timed_out": False,
            "overflow": False,
        }

    def docker(command, **kwargs):
        nonlocal container_name
        if command[1] == "create":
            container_name = command[command.index("--name") + 1]
            return subprocess.CompletedProcess(command, 0, b"container-id\n", b"")
        if command[1] == "rm":
            assert command == ["docker", "rm", "-f", container_name]
            return subprocess.CompletedProcess(command, 1, b"", b"removal failed")
        assert command[1] == "ps" and "-a" in command and f"name=^/{container_name}$" in command
        return subprocess.CompletedProcess(
            command,
            int(cleanup_state == "daemon_down"),
            b"container-id\n" if cleanup_state == "still_present" else b"",
            b"",
        )

    monkeypatch.setattr(_sandbox, "capture", successful_capture)
    monkeypatch.setattr(subprocess, "run", docker)
    sandbox = _sandbox.ContainerSandbox()
    if cleanup_state == "already_removed":
        assert sandbox.run("pass", {}, []).ok
    else:
        with pytest.raises(RuntimeError, match="sandbox cleanup"):
            sandbox.run("pass", {}, [])


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/tmp/escape",
        "a/../../escape",
        "a//b",
        "a/./b",
        "C:/escape",
        "a\\b",
        "__program__.py",
        "__transport__.py",
    ],
)
def test_untrusted_staged_paths_rejected(name):
    with pytest.raises(ValueError):
        prepare_workdir("pass", {name: "untrusted"})


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"stdout": [], "stderr": "", "error": None, "vars": {}},
        {"stdout": "", "stderr": "", "error": None, "vars": {"x": float("nan")}},
    ],
)
def test_malformed_grade_result_rejected(value):
    with pytest.raises(ValueError):
        _validate_result(value)


@pytest.mark.parametrize(
    "program,artifacts",
    [
        ("import os\nwhile True: os.write(1,b'x'*8192)", []),
        ("import os\nwhile True: os.write(2,b'x'*8192)", []),
        ("open('/output/large','wb').write(b'x'*(1024*1024+1))", ["large"]),
        ("import os; os.symlink('/etc/passwd','/output/escape')", ["escape"]),
        ("import os; os.symlink('/etc','/output/d');", ["d/passwd"]),
        ("import os; os.mkfifo('/output/pipe')", ["pipe"]),
        ("open('/output/a','w').write('x');import os;os.link('/output/a','/output/b')", ["a"]),
        ("open('/output/huge','wb').write(b'x'*(10*1024*1024))", []),
    ],
)
def test_real_container_rejects_output_and_artifact_attacks(program, artifacts):
    r = run_python(program, artifacts=artifacts, wall_seconds=10)
    assert not r.ok
    assert not r.artifacts
    assert len(r.stdout.encode()) + len(r.stderr.encode()) <= 3 * 256 * 1024


def test_safe_structured_values_survive():
    value = {
        "stdout": "hi",
        "stderr": "",
        "error": None,
        "vars": {
            "x": [1, 2.5],
            "df": {"__belay_type__": "dataframe", "columns": ["a"], "data": [[1]]},
        },
    }
    assert _validate_result(json.loads(json.dumps(value))) == value
