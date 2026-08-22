# SPDX-License-Identifier: AGPL-3.0-only

"""
Container-based sandbox for untrusted student code (CC-B4).
"""

from __future__ import annotations

import os
import subprocess
import time

from . import RunnerResult
from ._utils import cleanup_workdir, collect_artifacts, prepare_workdir


class ContainerSandbox:
    """Docker-based sandbox for executing untrusted Python code."""

    def __init__(
        self,
        cpu_seconds: int = 10,
        memory_mb: int = 256,
        wall_seconds: float = 20.0,
        use_gvisor: bool = False,
    ):
        self.cpu_seconds = cpu_seconds
        self.memory_mb = memory_mb
        self.wall_seconds = wall_seconds
        self.use_gvisor = use_gvisor

    def run(
        self, program: str, files: dict[str, str | bytes], artifacts: list[str]
    ) -> RunnerResult:
        """Execute the program in a container and return RunnerResult."""

        workdir, _prog_path = prepare_workdir(program, files, prefix="ptf_container_")

        try:
            cmd = self._build_docker_command(workdir)

            t0 = time.perf_counter()
            timed_out = False
            error: str | None = None
            stdout: str = ""
            stderr: str = ""
            exit_code: int | None = None

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.wall_seconds,
                )
                stdout = result.stdout or ""
                stderr = result.stderr or ""
                exit_code = result.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                out = exc.stdout
                stdout = out.decode("utf-8") if isinstance(out, bytes) else (out or "")
                err = exc.stderr
                stderr = err.decode("utf-8") if isinstance(err, bytes) else (err or "")
                error = f"container timeout after {self.wall_seconds}s"
                subprocess.run(["docker", "rm", "-f", "ptf-sandbox"], capture_output=True)

            wall_ms = round((time.perf_counter() - t0) * 1000, 1)

            collected = collect_artifacts(workdir, artifacts)

            ok = (not timed_out) and exit_code == 0

            return RunnerResult(
                ok=ok,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                wall_ms=wall_ms,
                error=error,
                artifacts=collected,
            )

        finally:
            cleanup_workdir(workdir)

    def _build_docker_command(self, workdir: str) -> list[str]:
        """Build the Docker run command with sandbox flags."""
        image = "belay-sandbox:0.1.0"

        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000

        cmd = [
            "docker",
            "run",
            "--rm",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            f"{self.memory_mb}m",
            "--memory-swap",
            f"{self.memory_mb}m",
            "--cpus",
            "1.0",
            "--network",
            "none",
            "--tmpfs",
            "/tmp:rw,size=64m",
            "--user",
            f"{uid}:{gid}",
            "-v",
            f"{workdir}:/workspace:rw",
            "-w",
            "/workspace",
        ]

        if self.use_gvisor:
            cmd.extend(["--runtime", "runsc"])

        cmd.extend(
            [
                image,
                "python",
                "-I",
                "/workspace/__program__.py",
            ]
        )

        return cmd
