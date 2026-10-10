# SPDX-License-Identifier: AGPL-3.0-only
"""Operator-only inspection and evidence-backed reconciliation, never HTTP routes."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from .admission import Admission, jobs, opaque, slots
from .contracts import Amount, ControlError
from .ledger import Ledger, attempts, reconciliations


def snapshot(ledger: Ledger) -> dict:
    output: dict = {}
    with ledger.transaction() as conn:
        now = ledger.now(conn)
        Admission(ledger)._expire(conn, now)
        work = list(conn.execute(select(jobs)).mappings())
        resources = list(conn.execute(select(slots)).mappings())
        waiting = [r for r in work if r["state"] == "queued"]
        output["queue"] = {
            "depth": len(waiting),
            "bytes": sum(r["payload_bytes"] for r in waiting),
            "oldest_wait_seconds": max((now - r["created"] for r in waiting), default=0),
        }
        output["jobs"] = {
            state: sum(r["state"] == state for r in work)
            for state in (
                "queued",
                "running",
                "cancel_requested",
                "unknown",
                "completed",
                "failed",
                "cancelled",
            )
        }
        output["slots"] = {
            kind: {
                state: sum(r["kind"] == kind and r["state"] == state for r in resources)
                for state in ("active", "unknown")
            }
            for kind in ("model", "runner")
        }
        output["reconciliations"] = len(list(conn.execute(select(reconciliations.c.id))))
    return ledger.summary() | output


def unresolved(ledger: Ledger) -> list[dict]:
    with ledger.transaction() as conn:
        return [
            dict(r)
            for r in conn.execute(
                select(
                    attempts.c.id,
                    attempts.c.operation,
                    attempts.c.kind,
                    attempts.c.state,
                    attempts.c.reserved,
                    attempts.c.actual,
                    attempts.c.created,
                ).where(attempts.c.state.in_(["reserved", "unknown", "overrun"]))
            ).mappings()
        ]


def reconcile(
    ledger: Ledger, target: str, evidence: str, *, action: str, actual: Amount | None = None
) -> None:
    """Evidence is an opaque incident reference, not free text or learner content.

    Operator must obtain provider/runner evidence before confirming stopped work.
    Financial reconciliation and execution termination are separate assertions.
    """
    opaque(evidence)
    with ledger.transaction() as conn:
        if action == "settle_attempt":
            if actual is None:
                raise ValueError("actual usage required")
            row = conn.execute(select(attempts).where(attempts.c.id == target)).mappings().first()
            if row is None or row["state"] not in {"reserved", "unknown"}:
                raise ControlError("reconciliation_conflict", 409)
            state = (
                "overrun"
                if any(actual.model_dump()[u] > row["reserved"][u] for u in actual.model_dump())
                else "settled"
            )
            conn.execute(
                attempts.update()
                .where(attempts.c.id == target)
                .values(actual=actual.model_dump(), state=state)
            )
        elif action == "confirm_stopped":
            # Unknown jobs are closed as failed, never blindly requeued. Budget
            # holds remain until separately reconciled from authoritative usage.
            resource = conn.execute(select(slots.c.id).where(slots.c.operation == target)).first()
            job = conn.execute(select(jobs.c.id).where(jobs.c.id == target)).first()
            if resource is None and job is None:
                raise ControlError("reconciliation_conflict", 409)
            conn.execute(slots.update().where(slots.c.operation == target).values(state="released"))
            conn.execute(
                jobs.update()
                .where(
                    jobs.c.id == target,
                    jobs.c.state.in_(["running", "cancel_requested", "unknown"]),
                )
                .values(
                    state="failed", reason="externally_stopped", payload_ref=None, result_ref=None
                )
            )
        elif action == "acknowledge_overrun":
            row = conn.execute(select(attempts).where(attempts.c.id == target)).mappings().first()
            if row is None or row["state"] != "overrun":
                raise ControlError("reconciliation_conflict", 409)
        else:
            raise ValueError("invalid reconciliation action")
        conn.execute(
            reconciliations.insert().values(
                id=uuid.uuid4().hex,
                target=target,
                action=action,
                evidence=evidence,
                created=ledger.now(conn),
            )
        )
