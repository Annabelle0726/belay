# SPDX-License-Identifier: AGPL-3.0-only
"""Bound pipe capture during reading, not after unbounded allocation."""

import os
import signal
import subprocess
import threading
import time
from typing import Any


def capture(command, *, limit, timeout, env=None, cwd=None, stop=None) -> dict[str, Any]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
        start_new_session=True,
    )
    buffers = [bytearray(), bytearray()]
    size = 0
    lock = threading.Lock()
    overflow = threading.Event()

    def drain(pipe, index):
        nonlocal size
        try:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    break
                with lock:
                    room = max(0, limit - size)
                    buffers[index].extend(chunk[:room])
                    size += min(room, len(chunk))
                    if len(chunk) > room:
                        overflow.set()
        finally:
            pipe.close()

    threads = [
        threading.Thread(target=drain, args=(pipe, i), daemon=True)
        for i, pipe in enumerate([process.stdout, process.stderr])
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        while process.poll() is None:
            if overflow.is_set() or time.monotonic() >= deadline:
                timed_out = not overflow.is_set()
                if stop is not None:
                    stop()
                if process.poll() is None:
                    process.kill()
                break
            time.sleep(0.01)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
        # A forked child must not keep the capture pipes or process group alive.
        if os.name == "posix":
            try:
                kill_group = getattr(os, "killpg", None)
                if callable(kill_group):
                    kill_group(process.pid, getattr(signal, "SIGKILL", 9))
            except ProcessLookupError:
                pass
        for thread in threads:
            thread.join(timeout=2)
    return {
        "stdout": bytes(buffers[0]),
        "stderr": bytes(buffers[1]),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "overflow": overflow.is_set(),
    }
