# SPDX-License-Identifier: AGPL-3.0-only
"""Content-free deletion fences kept independently of restorable dialogue backups."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import HTTPException


class DeletionLedger:
    def __init__(self, path: str):
        self.path = Path(path)

    def initialize(self) -> None:
        # Deployment only; API workers never silently create a fresh/empty ledger.
        if self.path.exists():
            self.deleted()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, b'{"schema":1}\n')
            os.fsync(fd)
        finally:
            os.close(fd)

    def deleted(self) -> set[str]:
        try:
            raw = self.path.read_text(encoding="utf-8")
            if not raw.endswith("\n"):
                raise ValueError
            lines = [json.loads(line) for line in raw.splitlines()]
            if not lines or lines[0] != {"schema": 1}:
                raise ValueError
            result = set()
            for item in lines[1:]:
                cid = item["conversation_id"]
                if (
                    set(item) != {"conversation_id"}
                    or not isinstance(cid, str)
                    or len(cid) != 32
                    or any(c not in "0123456789abcdef" for c in cid)
                ):
                    raise ValueError
                result.add(cid)
            return result
        except (OSError, ValueError, TypeError, KeyError):
            raise HTTPException(503, "dialogue deletion ledger unavailable") from None

    def record(self, cid: str) -> None:
        self.deleted()
        payload = json.dumps({"conversation_id": cid}, separators=(",", ":")).encode() + b"\n"
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND)
            try:
                # One small append. Partial/corrupted tails fail closed on all readers.
                if os.write(fd, payload) != len(payload):
                    raise OSError
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            raise HTTPException(503, "dialogue deletion ledger unavailable") from None
