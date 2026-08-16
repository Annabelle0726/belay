# backend/app/core/runner/_sandbox.py

# SPDX-License-Identifier: AGPL-3.0-only
"""
Container-based sandbox for untrusted student code (CC-B4).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import uuid

from . import RunnerResult


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
        self,
        program: str,
        files: dict[str, str | bytes],
        artifacts: list[str],
    ) -> RunnerResult:
        """Execute the program in a container and return RunnerResult."""
        workdir = tempfile.mkdtemp(prefix="ptf_container_")
        container_name = f"ptf-sandbox-{uuid.uuid4().hex[:8]}"

        try:
            # Write program file
            prog_path = os.path.join(workdir, "__program__.py")
            with open(prog_path, "w", encoding="utf-8") as fh:
                fh.write(program)

            # Write additional files
            for name, content in files.items():
                dest = os.path.join(workdir, name)
                parent = os.path.dirname(dest)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                if isinstance(content, bytes):
                    with open(dest, "wb") as fh:
                        fh.write(content)
                else:
                    with open(dest, "w", encoding="utf-8") as fh:
                        fh.write(content)

            # Build Docker command
            cmd = self._build_docker_command(workdir, container_name)

            # Run container
            t0 = time.perf_counter()
            timed_out = False
            error = None
            stdout = ""
            stderr = ""
            exit_code = None

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.wall_seconds + 10,  # Give extra time for pip install
                )
                stdout = result.stdout
                stderr = result.stderr
                exit_code = result.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = exc.stdout or ""
                stderr = exc.stderr or ""
                error = f"container timeout after {self.wall_seconds}s"
                # Kill the container if it's still running
                subprocess.run(["docker", "kill", container_name], capture_output=True)
                subprocess.run(["docker", "rm", container_name], capture_output=True)

            wall_ms = round((time.perf_counter() - t0) * 1000, 1)

            # Collect artifacts from host workdir (mounted volume)
            collected = {}
            for name in artifacts:
                path = os.path.join(workdir, name)
                if os.path.exists(path):
                    try:
                        with open(path, encoding="utf-8", errors="replace") as fh:
                            collected[name] = fh.read()
                    except OSError:
                        pass

            ok = (not timed_out) and exit_code == 0

            return RunnerResult(
                ok=ok,
                exit_code=exit_code,
                stdout=stdout or "",
                stderr=stderr or "",
                timed_out=timed_out,
                wall_ms=wall_ms,
                error=error,
                artifacts=collected,
            )

        finally:
            # Clean up container and workdir
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)

    # backend/app/core/runner/_sandbox.py

    def _build_docker_command(self, workdir: str) -> list[str]:
        """Build the Docker run command with sandbox flags."""
        image = "belay-sandbox:0.1.0"

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
            "--tmpfs",
            "/workspace:rw,size=64m",  # 可写的工作目录
            "--user",
            "sandbox",
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
