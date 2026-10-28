# SPDX-License-Identifier: AGPL-3.0-only
"""Container-only supervision, no reference solutions or grading authority."""

import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._artifacts import collect_safe
    from ._bounded import capture

CHILD_WALL_SECONDS: float = globals().get("CHILD_WALL_SECONDS", 20.0)
REQUESTED_ARTIFACTS: list[str] = globals().get("REQUESTED_ARTIFACTS", [])


def main():
    # Helpers are concatenated from trusted read-only source by the host.
    outcome = capture(
        [sys.executable, "-I", "-u", "/workspace/__program__.py"],
        limit=256 * 1024,
        timeout=CHILD_WALL_SECONDS,
        cwd="/workspace",
    )
    error = (
        "output limit exceeded"
        if outcome["overflow"]
        else "execution timeout"
        if outcome["timed_out"]
        else None
    )
    artifacts = {}
    if error is None:
        try:
            artifacts = collect_safe("/output", REQUESTED_ARTIFACTS)
        except (OSError, ValueError):
            error = "artifact boundary rejected"
    result = {
        "exit_code": outcome["exit_code"],
        "stdout": outcome["stdout"].decode("utf-8", errors="replace"),
        "stderr": outcome["stderr"].decode("utf-8", errors="replace"),
        "timed_out": outcome["timed_out"],
        "error": error,
        "artifacts": artifacts,
    }
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
