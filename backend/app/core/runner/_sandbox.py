# SPDX-License-Identifier: AGPL-3.0-only

"""
Container-based sandbox for untrusted student code (CC-B4).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from . import RunnerResult
from ._artifacts import MAX_ARTIFACT_TOTAL, MAX_ARTIFACTS, parts
from ._bounded import capture
from ._utils import cleanup_workdir, prepare_workdir, safe_decode

MAX_RESULT_BYTES = 8 * 1024 * 1024


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
        """
        Execute the program in a container and return RunnerResult.

        Security properties:
        - Read-only root filesystem (--read-only)
        - CPU time limit via --ulimit cpu
        - Wall clock timeout via subprocess timeout
        - Process limit via --pids-limit
        - Memory limit via --memory
        - No network via --network none
        - Unique container name for reliable cleanup
        """
        if len(artifacts) > MAX_ARTIFACTS:
            raise ValueError("artifact count exceeded")
        for name in artifacts:
            parts(name)
        workdir = prepare_workdir(program, files, prefix="ptf_container_")
        container_name = f"ptf-sandbox-{uuid.uuid4().hex[:12]}"

        def remove():
            for attempt in range(2):
                try:
                    subprocess.run(
                        ["docker", "rm", "-f", container_name], capture_output=True, timeout=15
                    )
                    return
                except subprocess.TimeoutExpired:
                    if attempt:
                        raise RuntimeError("sandbox cleanup unavailable") from None

        try:
            directory = Path(__file__).parent
            helpers = "\n".join(
                (directory / name).read_text(encoding="utf-8")
                for name in ["_bounded.py", "_artifacts.py"]
            )
            transport = (directory / "_transport.py").read_text(encoding="utf-8")
            source = (
                helpers
                + "\nCHILD_WALL_SECONDS="
                + repr(self.wall_seconds)
                + "\nREQUESTED_ARTIFACTS="
                + repr(artifacts)
                + "\n"
                + transport
            )
            Path(workdir, "__transport__.py").write_text(source, encoding="utf-8")
            os.chmod(Path(workdir, "__transport__.py"), 0o644)
            t0 = time.perf_counter()
            result = capture(
                self._build_docker_command(workdir, "", container_name),
                limit=MAX_RESULT_BYTES,
                timeout=self.wall_seconds,
                stop=remove,
            )
            wall_ms = round((time.perf_counter() - t0) * 1000, 1)
            if result["timed_out"] or result["overflow"]:
                return RunnerResult(
                    False,
                    result["exit_code"],
                    "",
                    safe_decode(result["stderr"]),
                    result["timed_out"],
                    wall_ms,
                    "output limit exceeded" if result["overflow"] else "execution timeout",
                    {},
                )
            try:
                data = json.loads(result["stdout"])
                if not isinstance(data, dict) or set(data) != {
                    "exit_code",
                    "stdout",
                    "stderr",
                    "timed_out",
                    "error",
                    "artifacts",
                }:
                    raise ValueError
                if (
                    type(data["exit_code"]) is not int
                    or type(data["timed_out"]) is not bool
                    or not isinstance(data["stdout"], str)
                    or not isinstance(data["stderr"], str)
                    or data["error"]
                    not in (
                        None,
                        "output limit exceeded",
                        "execution timeout",
                        "artifact boundary rejected",
                    )
                    or not isinstance(data["artifacts"], dict)
                    or len(data["artifacts"]) > MAX_ARTIFACTS
                    or any(
                        k not in artifacts or not isinstance(v, str)
                        for k, v in data["artifacts"].items()
                    )
                    or sum(len(v.encode()) for v in data["artifacts"].values())
                    > MAX_ARTIFACT_TOTAL * 3
                    or len(data["stdout"].encode()) + len(data["stderr"].encode()) > 256 * 1024 * 3
                ):
                    raise ValueError
            except (ValueError, TypeError):
                return RunnerResult(
                    False,
                    result["exit_code"],
                    "",
                    safe_decode(result["stderr"]),
                    False,
                    wall_ms,
                    "invalid execution envelope",
                    {},
                )
            return RunnerResult(
                result["exit_code"] == 0
                and data["exit_code"] == 0
                and not data["timed_out"]
                and data["error"] is None,
                data["exit_code"],
                data["stdout"],
                data["stderr"],
                data["timed_out"],
                wall_ms,
                data["error"],
                data["artifacts"],
            )
        finally:
            try:
                remove()
            finally:
                cleanup_workdir(workdir)

    def _build_docker_command(
        self, workdir: str, output_dir: str, container_name: str
    ) -> list[str]:
        """
        Build the Docker run command with sandbox flags.

        Security flags:
        - --read-only: root filesystem is read-only
        - --cap-drop ALL: drop all Linux capabilities
        - --security-opt no-new-privileges: prevent privilege escalation
        - --pids-limit 64: limit number of processes (fork bomb protection)
        - --memory + --memory-swap: memory limit with swap disabled
        - --ulimit cpu: CPU time limit (real CPU time, not just share)
        - --network none: empty network namespace (not just socket patch)
        - --tmpfs: writable temp space with size cap
        - --user: run as non-root user with host UID/GID mapping
        """
        image = "belay-sandbox:0.1.0"

        uid = (os.getuid() or 65534) if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000

        cmd = [
            "docker",
            "run",
            "--rm",
            "--read-only",
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
            "--ulimit",
            f"cpu={self.cpu_seconds}:{self.cpu_seconds + 1}",
            "--network",
            "none",
            "--tmpfs",
            "/tmp:rw,size=64m",
            "--user",
            f"{uid}:{gid}",
            "--name",
            container_name,
            "-v",
            f"{workdir}:/workspace:ro",
            "--tmpfs",
            "/output:rw,size=8m,mode=1777,nodev,nosuid,noexec",
            "-w",
            "/workspace",
        ]

        if self.use_gvisor:
            cmd.extend(["--runtime", "runsc"])

        cmd.extend(
            [
                image,
                "python",
                "-u",
                "-I",
                "/workspace/__transport__.py",
            ]
        )

        return cmd
