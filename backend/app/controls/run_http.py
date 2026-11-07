# SPDX-License-Identifier: AGPL-3.0-only
"""Trusted accounting context for the existing synchronous code-run endpoint."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from ..auth import Identity, capture_assignment_access, recheck_grant
from ..config import settings
from .runtime import current, operation


@contextmanager
def run_context(identity: Identity) -> Iterator[None]:
    grant = capture_assignment_access(identity, "run")

    def guard() -> None:
        recheck_grant(grant)

    if settings.controls_mode != "enforced":
        current()  # Budget bypass never bypasses course authorization.
        guard()
        yield
        guard()
        return
    from .jobs_http import execution_store

    store = execution_store()  # Existing configuration/schema; never initialize.

    # Each deliberate Run is one synchronous operation, not a model/queue job.
    # runner_call still reserves and settles each actual sandbox attempt.
    with operation(
        store.ledger,
        store.scope(identity),
        "run-" + uuid.uuid4().hex,
        guard=guard,
    ):
        current()
        yield
        current()  # Do not release a result using revoked submission authority.
