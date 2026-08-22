# SPDX-License-Identifier: AGPL-3.0-only

import os
import tempfile


def prepare_workdir(
    program: str,
    files: dict[str, str | bytes] | None = None,
    prefix: str = "ptf_runner_",
) -> tuple[str, str]:
    """
    Create a temporary working directory and write program and files.

    Returns:
        (workdir_path, program_path)
    """
    workdir = tempfile.mkdtemp(prefix=prefix)

    os.chmod(workdir, 0o777)

    prog_path = os.path.join(workdir, "__program__.py")
    with open(prog_path, "w", encoding="utf-8") as fh:
        fh.write(program)
    os.chmod(prog_path, 0o644)

    for name, content in (files or {}).items():
        dest = os.path.join(workdir, name)
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
            os.chmod(parent, 0o777)
        if isinstance(content, bytes):
            with open(dest, "wb") as fh:
                fh.write(content)
        else:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(content)
        os.chmod(dest, 0o644)

    return workdir, prog_path


def collect_artifacts(workdir: str, artifacts: list[str]) -> dict[str, str]:
    """Collect artifact files from the workdir."""
    collected = {}
    for name in artifacts or []:
        path = os.path.join(workdir, name)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    collected[name] = fh.read()
            except OSError:
                pass
    return collected


def cleanup_workdir(workdir: str) -> None:
    """Remove the temporary working directory."""
    import shutil

    shutil.rmtree(workdir, ignore_errors=True)
