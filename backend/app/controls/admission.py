# SPDX-License-Identifier: AGPL-3.0-only
"""Shared bounded job scheduling. Payload/result references are opaque IDs.

This service accepts trusted scopes. It is not an HTTP authentication layer.
Caller supplies short-lived data storage and reauthorization at dispatch and
publication; no bearer token or learner content is stored here.
"""

from __future__ import annotations

import hashlib
import re
import uuid

from sqlalchemy import JSON, Column, Float, Integer, String, Table, func, select
from sqlalchemy.engine import Connection

from .contracts import Amount, ControlError, Scope
from .ledger import Ledger, attempts, metadata

jobs = Table(
    "control_jobs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("operation", String(128), nullable=False),
    Column("scopes", JSON, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("payload_ref", String(64)),
    Column("payload_bytes", Integer, nullable=False),
    Column("result_ref", String(64)),
    Column("state", String(24), nullable=False, index=True),
    Column("reason", String(64)),
    Column("created", Float, nullable=False),
    Column("expires", Float, nullable=False),
    Column("lease", Float),
    Column("fence", Integer, nullable=False),
    Column("last_poll", Float),
    Column("sequence", Integer, nullable=False),
)
buckets = Table(
    "control_buckets",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tokens", Float, nullable=False),
    Column("updated", Float, nullable=False),
)
rotation = Table(
    "control_rotation",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("served", Integer, nullable=False),
)
slots = Table(
    "control_slots",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("scopes", JSON, nullable=False),
    Column("operation", String(128), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("state", String(16), nullable=False),
    Column("created", Float, nullable=False),
)

ACTIVE = {"running", "cancel_requested", "unknown"}


def opaque(value: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32,64}", value):
        raise ValueError("expected opaque hexadecimal reference")


class Admission:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    def _release_queue(self, conn: Connection, job_id: str) -> None:
        conn.execute(
            attempts.update()
            .where(attempts.c.id == "queue:" + job_id)
            .values(state="settled", actual=Amount().model_dump())
        )

    def _expire(self, conn: Connection, now: float) -> None:
        for row in conn.execute(select(jobs).where(jobs.c.state == "queued")).mappings():
            if row["expires"] <= now:
                self._release_queue(conn, row["id"])
                conn.execute(
                    jobs.update()
                    .where(jobs.c.id == row["id"])
                    .values(state="failed", reason="queue_expired", payload_ref=None)
                )
        conn.execute(
            jobs.update()
            .where(jobs.c.state.in_(["running", "cancel_requested"]), jobs.c.lease <= now)
            .values(state="unknown", reason="worker_lost", payload_ref=None)
        )

    def submit(
        self,
        scope: Scope,
        operation_id: str,
        fingerprint: str,
        payload_ref: str,
        payload_bytes: int,
        allowance: Amount,
    ) -> dict:
        opaque(fingerprint)
        opaque(payload_ref)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation_id):
            raise ValueError("invalid operation ID")
        keys = list(scope.keys())
        job_id = hashlib.sha256((keys[-1] + ":" + operation_id).encode()).hexdigest()
        with self.ledger.transaction() as conn:
            policy = self.ledger.policy(conn)
            now = self.ledger.now(conn)
            self._expire(conn, now)
            old = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise ControlError("operation_conflict", 409)
                return self._public(dict(old))
            if type(payload_bytes) is not int or not 0 <= payload_bytes <= policy.payload_bytes:
                raise ControlError("payload_too_large", 413)
            queued = list(conn.execute(select(jobs).where(jobs.c.state == "queued")).mappings())
            for key, cap in zip(keys, policy.traffic(), strict=True):
                owned = [j for j in queued if key in j["scopes"]]
                if (
                    len(owned) >= cap.queue_jobs
                    or sum(j["payload_bytes"] for j in owned) + payload_bytes > cap.queue_bytes
                ):
                    raise ControlError("queue_full", retry_after=policy.poll_seconds)
                bucket = conn.execute(select(buckets).where(buckets.c.id == key)).mappings().first()
                tokens = (
                    min(
                        cap.burst,
                        bucket["tokens"]
                        + max(0, now - bucket["updated"]) * cap.burst / cap.rate_seconds,
                    )
                    if bucket
                    else float(cap.burst)
                )
                if tokens < 1:
                    raise ControlError("rate_limited", retry_after=cap.rate_seconds)
                if bucket:
                    conn.execute(
                        buckets.update()
                        .where(buckets.c.id == key)
                        .values(tokens=tokens - 1, updated=now)
                    )
                else:
                    conn.execute(buckets.insert().values(id=key, tokens=tokens - 1, updated=now))
            self.ledger.reserve_in(conn, "queue:" + job_id, job_id, scope, allowance, "queue")
            row = dict(
                id=job_id,
                operation=operation_id,
                scopes=keys,
                fingerprint=fingerprint,
                payload_ref=payload_ref,
                payload_bytes=payload_bytes,
                result_ref=None,
                state="queued",
                reason=None,
                created=now,
                expires=now + policy.queue_wait_seconds,
                lease=None,
                fence=0,
                last_poll=None,
                sequence=(conn.execute(select(func.max(jobs.c.sequence))).scalar() or 0) + 1,
            )
            conn.execute(jobs.insert().values(**row))
            return self._public(row)

    def claim(self) -> dict | None:
        """Atomic class rotation/FIFO; returns a fenced claim requiring reauthorization."""
        with self.ledger.transaction() as conn:
            now = self.ledger.now(conn)
            self._expire(conn, now)
            policy = self.ledger.policy(conn)
            active = list(conn.execute(select(jobs).where(jobs.c.state.in_(ACTIVE))).mappings())
            served = {r["id"]: r["served"] for r in conn.execute(select(rotation)).mappings()}
            waiting = list(
                conn.execute(
                    select(jobs).where(jobs.c.state == "queued").order_by(jobs.c.sequence)
                ).mappings()
            )
            waiting.sort(key=lambda j: served.get(j["scopes"][2], 0))
            seen = set()
            for job in waiting:
                classroom = job["scopes"][2]
                if classroom in seen:
                    continue
                seen.add(classroom)
                if any(
                    sum(key in j["scopes"] for j in active) >= cap.active_jobs
                    for key, cap in zip(job["scopes"], policy.traffic(), strict=True)
                ):
                    continue
                # Recheck funding under current policy, including old queue holds.
                period = int(now) // policy.period_seconds
                eligible = True
                for key, cap in zip(job["scopes"], policy.limits(), strict=True):
                    usage = self.ledger._usage(conn, key, period)
                    if any(
                        limit is not None and usage[unit] > limit
                        for unit, limit in cap.model_dump().items()
                    ):
                        eligible = False
                if not eligible:
                    continue
                self._release_queue(conn, job["id"])
                # Funding is checked again before every external attempt. Dispatch
                # does not promise that an entire multi-attempt turn will finish.
                changes = dict(
                    state="running", fence=job["fence"] + 1, lease=now + policy.lease_seconds
                )
                conn.execute(jobs.update().where(jobs.c.id == job["id"]).values(**changes))
                seq = max(served.values(), default=0) + 1
                if classroom in served:
                    conn.execute(
                        rotation.update().where(rotation.c.id == classroom).values(served=seq)
                    )
                else:
                    conn.execute(rotation.insert().values(id=classroom, served=seq))
                return dict(job) | changes
            return None

    def _owned(self, conn: Connection, scope: Scope, job_id: str) -> dict:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
        if row is None or row["scopes"] != list(scope.keys()):
            raise ControlError("job_unavailable", 404)
        return dict(row)

    def _public(self, row: dict) -> dict:
        return {k: row[k] for k in ("id", "state", "reason", "result_ref")}

    def status(self, scope: Scope, job_id: str) -> dict:
        with self.ledger.transaction() as conn:
            now = self.ledger.now(conn)
            self._expire(conn, now)
            row = self._owned(conn, scope, job_id)
            interval = self.ledger.policy(conn).poll_seconds
            if row["last_poll"] is not None and now - row["last_poll"] < interval:
                raise ControlError("poll_limited", retry_after=interval)
            conn.execute(jobs.update().where(jobs.c.id == job_id).values(last_poll=now))
            return self._public(row)

    def cancel(self, scope: Scope, job_id: str) -> dict:
        with self.ledger.transaction() as conn:
            row = self._owned(conn, scope, job_id)
            state = row["state"]
            if state == "queued":
                self._release_queue(conn, job_id)
                state = "cancelled"
            elif state == "running":
                state = "cancel_requested"
            conn.execute(
                jobs.update().where(jobs.c.id == job_id).values(state=state, payload_ref=None)
            )
            return self._public(row | {"state": state})

    def heartbeat(self, job_id: str, fence: int) -> None:
        with self.ledger.transaction() as conn:
            row = self._live(conn, job_id, fence)
            if row["state"] == "cancel_requested":
                raise ControlError("cancel_requested", 409)
            conn.execute(
                jobs.update()
                .where(jobs.c.id == job_id)
                .values(lease=self.ledger.now(conn) + self.ledger.policy(conn).lease_seconds)
            )

    def _live(self, conn: Connection, job_id: str, fence: int) -> dict:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
        if (
            row is None
            or row["fence"] != fence
            or row["state"] not in {"running", "cancel_requested"}
            or row["lease"] <= self.ledger.now(conn)
        ):
            raise ControlError("stale_worker", 409)
        return dict(row)

    def finish(
        self, job_id: str, fence: int, result_ref: str | None = None, *, authorized: bool
    ) -> None:
        if result_ref:
            opaque(result_ref)
        with self.ledger.transaction() as conn:
            row = self._live(conn, job_id, fence)
            state = "completed" if authorized else "failed"
            reason = None if authorized else "authorization_revoked"
            if row["state"] == "cancel_requested":
                state, reason = "cancelled", None
            conn.execute(
                jobs.update()
                .where(jobs.c.id == job_id)
                .values(
                    state=state,
                    reason=reason,
                    result_ref=result_ref if state == "completed" else None,
                    payload_ref=None,
                )
            )

    def acquire_slot(self, scope: Scope, operation: str, kind: str) -> str:
        if kind not in {"model", "runner"}:
            raise ValueError("invalid concurrency resource")
        keys = list(scope.keys())
        with self.ledger.transaction() as conn:
            policy = self.ledger.policy(conn)
            active = list(
                conn.execute(
                    select(slots).where(
                        slots.c.kind == kind, slots.c.state.in_(["active", "unknown"])
                    )
                ).mappings()
            )
            for key, cap in zip(keys, policy.traffic(), strict=True):
                if sum(key in row["scopes"] for row in active) >= getattr(cap, kind + "_calls"):
                    raise ControlError("concurrency_limited", retry_after=policy.poll_seconds)
            slot_id = uuid.uuid4().hex
            conn.execute(
                slots.insert().values(
                    id=slot_id,
                    scopes=keys,
                    operation=operation,
                    kind=kind,
                    state="active",
                    created=self.ledger.now(conn),
                )
            )
            return slot_id

    def release_slot(self, slot_id: str, *, stopped: bool) -> None:
        with self.ledger.transaction() as conn:
            conn.execute(
                slots.update()
                .where(slots.c.id == slot_id)
                .values(state="released" if stopped else "unknown")
            )
