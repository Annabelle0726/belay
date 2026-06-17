"""
core/runner — the single restricted execution path for untrusted student code.

Every pack execution path (``run``, ``verify_worked_example``, ``leak_evidence``)
routes student code through `run_python`. Nothing executes student code in the
main process.

THREAT MODEL (stated honestly):
  This is a **resource, network, and isolation boundary, NOT adversarial
  containment.** It runs code in a separate, isolated-temp-cwd subprocess with:
    - CPU-seconds and wall-clock limits (always; wall is the hard stop),
    - an optional address-space/memory limit (RLIMIT_AS/DATA — enforced on Linux,
      best-effort on macOS where virtual-memory accounting is unreliable),
    - the network made unreachable at the process level (socket connect paths
      raise; numpy/pandas remain importable),
    - an isolated temp working directory, HOME and TMPDIR pointed at it, and
      ``python -I`` (ignore PYTHONPATH / user-site / PYTHON* env).
  A determined adversary on a shared host is NOT contained by this. The
  convergence point — and the closing step on the roadmap — is a **containerized
  runner** (matching Quad's ephemeral sandboxed graders) that adds an OS-level
  network namespace and filesystem/PID isolation. Until then this boundary is
  sized to the actual threat: a tutor or student program that is wrong, slow, or
  resource-hungry — not one mounting a sandbox escape.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

_CHILD = os.path.join(os.path.dirname(__file__), "_child.py")

# Defaults sized for a tutoring grader (numpy/pandas import + a tiny model).
DEFAULT_CPU_SECONDS = 10
DEFAULT_WALL_SECONDS = 20.0
DEFAULT_MEMORY_MB: int | None = None  # opt-in; see threat model (macOS caveat)


@dataclass
class RunnerResult:
    """Structured outcome of a sandboxed execution."""

    ok: bool  # process completed with exit code 0, no timeout
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    wall_ms: float
    error: str | None  # runner-level error (timeout / spawn failure)
    artifacts: dict[str, str] = field(default_factory=dict)


def run_python(
    program: str,
    *,
    files: dict[str, str | bytes] | None = None,
    artifacts: list[str] | None = None,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    memory_mb: int | None = DEFAULT_MEMORY_MB,
    wall_seconds: float = DEFAULT_WALL_SECONDS,
) -> RunnerResult:
    """Execute ``program`` (Python source) in the restricted sandbox.

    ``files`` are written into the isolated working directory before execution
    (relative names; nested paths allowed). ``artifacts`` names files to read back
    out of the workdir after the run. All student code MUST come through here.
    """
    workdir = tempfile.mkdtemp(prefix="ptf_runner_")
    try:
        prog_path = os.path.join(workdir, "__program__.py")
        with open(prog_path, "w", encoding="utf-8") as fh:
            fh.write(program)
        for name, content in (files or {}).items():
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

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": workdir,
            "TMPDIR": workdir,
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PTF_CPU_SECONDS": str(cpu_seconds),
            "PTF_MEMORY_MB": str(memory_mb or 0),
            # Keep BLAS single-threaded: deterministic + bounded CPU.
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }

        t0 = time.perf_counter()
        timed_out = False
        error: str | None = None
        try:
            proc = subprocess.run(
                [sys.executable, "-I", _CHILD, prog_path],
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=wall_seconds,
                start_new_session=True,
            )
            exit_code: int | None = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            stdout = exc.stdout or ""  # type: ignore[assignment]  # bytes|str|None; decoded to str next line
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            stderr = exc.stderr or ""  # type: ignore[assignment]  # bytes|str|None; decoded to str next line
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            error = f"wall timeout after {wall_seconds}s"
        wall_ms = round((time.perf_counter() - t0) * 1000, 1)

        collected: dict[str, str] = {}
        for name in artifacts or []:
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
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = [
    "run_python",
    "RunnerResult",
    "DEFAULT_CPU_SECONDS",
    "DEFAULT_WALL_SECONDS",
    "DEFAULT_MEMORY_MB",
]
