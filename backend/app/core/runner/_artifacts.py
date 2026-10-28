# SPDX-License-Identifier: AGPL-3.0-only
"""Descriptor-relative bounded artifact reads; unsupported hosts fail closed."""

import os
import stat
from pathlib import PurePosixPath

MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_ARTIFACT_TOTAL = 1024 * 1024
MAX_ARTIFACTS = 16


def parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or len(name) > 256 or "\\" in name or ":" in name:
        raise ValueError("invalid artifact path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in (".", "..", "") for p in name.split("/")):
        raise ValueError("invalid artifact path")
    return path.parts


def collect_safe(directory: str, names: list[str]) -> dict[str, str]:
    if len(names) > MAX_ARTIFACTS:
        raise ValueError("artifact count exceeded")
    requested = [(name, parts(name)) for name in names]
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        return {}  # No check-then-open path fallback on Windows.
    result = {}
    used = 0
    root = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
    try:
        for name, path in requested:
            parent = os.dup(root)
            handle = None
            try:
                for segment in path[:-1]:
                    child = os.open(
                        segment,
                        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW,
                        dir_fd=parent,
                    )
                    os.close(parent)
                    parent = child
                handle = os.open(
                    path[-1],
                    os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                    dir_fd=parent,
                )
                info = os.fstat(handle)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("invalid artifact type")
                if info.st_size > MAX_ARTIFACT_BYTES or used + info.st_size > MAX_ARTIFACT_TOTAL:
                    raise ValueError("artifact size exceeded")
                chunks = []
                length = 0
                while True:
                    chunk = os.read(handle, min(8192, MAX_ARTIFACT_BYTES - length + 1))
                    if not chunk:
                        break
                    length += len(chunk)
                    if length > MAX_ARTIFACT_BYTES or used + length > MAX_ARTIFACT_TOTAL:
                        raise ValueError("artifact size exceeded")
                    chunks.append(chunk)
                used += length
                result[name] = b"".join(chunks).decode("utf-8", errors="replace")
            except FileNotFoundError:
                pass
            except OSError as error:
                raise ValueError("unsafe artifact path") from error
            finally:
                if handle is not None:
                    os.close(handle)
                os.close(parent)
    finally:
        os.close(root)
    return result
