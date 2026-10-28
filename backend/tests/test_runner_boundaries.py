# SPDX-License-Identifier: AGPL-3.0-only
import json
import sys
import time

import pytest

from app.core.runner import run_python
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
