# SPDX-License-Identifier: AGPL-3.0-only
"""Fenced worker seam. Auth/conversation adapters must be supplied by integration.

No raw credential is stored. check() must consult current membership, assignment
version, conversation deletion/revision and input TTL, rather than replaying an
admission-time grant. execute() must return an owned, expiring result reference.
"""

from __future__ import annotations

import threading
from typing import Protocol

from .admission import Admission
from .contracts import ControlError, Scope
from .runtime import operation


class JobAdapter(Protocol):
    def check(self, job: dict) -> Scope: ...
    def execute(self, job: dict) -> str: ...


def run_one(admission: Admission, adapter: JobAdapter) -> bool:
    job = admission.claim()
    if job is None:
        return False
    stopped = threading.Event()
    lost = threading.Event()

    def check() -> Scope:
        if lost.is_set():
            raise ControlError("worker_lease_lost", 409)
        scope = adapter.check(job)
        if list(scope.keys()) != job["scopes"]:
            raise ControlError("authorization_revoked", 403)
        admission.heartbeat(job["id"], job["fence"])
        return scope

    def guard() -> None:
        check()

    with admission.ledger.transaction() as conn:
        interval = min(30.0, admission.ledger.policy(conn).lease_seconds / 3)

    def heartbeat() -> None:
        while not stopped.wait(interval):
            try:
                guard()
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=heartbeat, daemon=True, name="belay-control-lease")
    try:
        scope = check()
        thread.start()
        with operation(admission.ledger, scope, job["id"], guard):
            result = adapter.execute(job)
        check()  # Never publish using admission-time authorization alone.
        admission.finish(job["id"], job["fence"], result, authorized=True)
    except Exception as exc:
        # No retries. Unknown external attempts/slots retain their liability.
        try:
            admission.finish(
                job["id"],
                job["fence"],
                authorized=False,
                failure_reason=exc.code if isinstance(exc, ControlError) else "execution_failed",
            )
        except ControlError:
            # A lost/expired fence cannot mutate the job or publish.
            pass
    finally:
        stopped.set()
        if thread.is_alive():
            thread.join(timeout=1)
    return True
