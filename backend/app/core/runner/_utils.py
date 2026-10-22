# SPDX-License-Identifier: AGPL-3.0-only

import os
import shutil
import tempfile

from ._artifacts import collect_safe, parts


def safe_decode(data: bytes | str | None) -> str:
    """Safely decode subprocess output to string, replacing invalid characters."""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def _write_files_to_dir(workdir: str, program: str, files: dict[str, str | bytes] | None) -> None:
    """
    Internal helper: write program and files to a directory.
    Sets appropriate permissions for container compatibility.
    """
    if len(program.encode()) > 1024 * 1024:
        raise ValueError("program limit exceeded")
    size = len(program.encode())
    for name, content in (files or {}).items():
        parts(name)
        if name in {"__program__.py", "__transport__.py"}:
            raise ValueError("reserved input path")
        size += len(content.encode()) if isinstance(content, str) else len(content)
        if size > 4 * 1024 * 1024:
            raise ValueError("input file limit exceeded")
    with open(os.path.join(workdir, "__program__.py"), "w", encoding="utf-8") as stream:
        stream.write(program)
    os.chmod(os.path.join(workdir, "__program__.py"), 0o644)
    for name, content in (files or {}).items():
        destination = os.path.join(workdir, *parts(name))
        os.makedirs(os.path.dirname(destination), mode=0o755, exist_ok=True)
        with open(destination, "wb") as stream:
            stream.write(content.encode() if isinstance(content, str) else content)
        os.chmod(destination, 0o644)


def prepare_workdir(
    program: str,
    files: dict[str, str | bytes] | None = None,
    prefix: str = "ptf_runner_",
) -> str:
    """
    Create a temporary working directory and write program and files.

    Returns:
        workdir_path
    """
    workdir = tempfile.mkdtemp(prefix=prefix)
    # Allow all users to read/write/execute (for container mount compatibility)
    os.chmod(workdir, 0o755)

    try:
        _write_files_to_dir(workdir, program, files)
        return workdir
    except Exception:
        cleanup_workdir(workdir)
        raise


def write_program_to_dir(
    workdir: str,
    program: str,
    files: dict[str, str | bytes] | None = None,
) -> None:
    """
    Write program and files to an existing directory.

    This is useful when you already have a workdir and want to populate it.
    """
    _write_files_to_dir(workdir, program, files)


def collect_artifacts(workdir: str, artifacts: list[str]) -> dict[str, str]:
    """Collect only bounded regular files through descriptor-relative access."""
    return collect_safe(workdir, artifacts or [])


def cleanup_workdir(workdir: str) -> None:
    """Remove the temporary working directory."""
    if workdir and os.path.exists(workdir):
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = [
    "safe_decode",
    "prepare_workdir",
    "write_program_to_dir",
    "collect_artifacts",
    "cleanup_workdir",
]
