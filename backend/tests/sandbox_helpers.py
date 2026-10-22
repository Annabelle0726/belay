# SPDX-License-Identifier: AGPL-3.0-only
import shutil
import subprocess

import pytest


def _docker_available() -> bool:
    """Check if Docker is available and running."""
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=20,
            check=True,
        )
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker unavailable; container tests run in CI",
)
