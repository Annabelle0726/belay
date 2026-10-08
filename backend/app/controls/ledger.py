# SPDX-License-Identifier: AGPL-3.0-only
"""Content-free ledger. Database transactions end before any external work.

A transaction advisory lock serializes coordinator mutations on PostgreSQL.
This intentionally trades throughput for an easily audited first coordinator.
SQLite BEGIN IMMEDIATE is a local-only implementation of the same contract.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import JSON, Column, Float, Integer, MetaData, String, Table, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from .contracts import UNITS, Amount, ControlError, Policy, Scope

metadata = MetaData()
configuration = Table(
    "control_configuration",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("policy", JSON, nullable=False),
)
attempts = Table(
    "control_attempts",
    metadata,
    Column("id", String(128), primary_key=True),
    Column("operation", String(128), nullable=False, index=True),
    Column("scopes", JSON, nullable=False),
    Column("period", Integer, nullable=False),
    Column("period_seconds", Integer, nullable=False),
    Column("policy", JSON, nullable=False),
    Column("kind", String(16), nullable=False),
    Column("reserved", JSON, nullable=False),
    Column("actual", JSON),
    Column("state", String(16), nullable=False),
    Column("created", Float, nullable=False),
)


class Ledger:
    def __init__(self, engine: Engine, clock: Callable[[], float] | None = None):
        if engine.dialect.name not in {"sqlite", "postgresql"}:
            raise ValueError("controls require PostgreSQL or local SQLite")
        self.engine, self.clock = engine, clock

    def initialize(self, policy: Policy) -> None:
        """Operator migration; never called automatically by an API worker."""
        from .admission import jobs

        assert jobs.metadata is metadata
        metadata.create_all(self.engine)
        with self.transaction() as conn:
            existing = conn.execute(select(configuration.c.policy)).scalar_one_or_none()
            if existing is None:
                conn.execute(configuration.insert().values(id=1, policy=policy.model_dump()))
            elif existing != policy.model_dump():
                raise ValueError("policy already installed; use explicit policy update")

    def update_policy(self, policy: Policy) -> None:
        with self.transaction() as conn:
            old = self.policy(conn)
            if policy.currency != old.currency or policy.period_seconds != old.period_seconds:
                raise ValueError("currency and period changes require a separate ledger migration")
            if policy.version == old.version:
                raise ValueError("policy update requires a new version")
            conn.execute(
                configuration.update()
                .where(configuration.c.id == 1)
                .values(policy=policy.model_dump())
            )

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        try:
            with self.engine.connect() as conn:
                if self.engine.dialect.name == "sqlite":
                    conn.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    conn.execute(text("SELECT pg_advisory_xact_lock(720316803)"))
                try:
                    yield conn
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
        except SQLAlchemyError as exc:
            raise ControlError("coordinator_unavailable", 503) from exc

    def now(self, conn: Connection) -> float:
        if self.clock:
            return self.clock()
        if self.engine.dialect.name == "postgresql":
            return float(
                conn.execute(text("SELECT EXTRACT(EPOCH FROM clock_timestamp())")).scalar_one()
            )
        return time.time()

    def policy(self, conn: Connection) -> Policy:
        raw = conn.execute(
            select(configuration.c.policy).where(configuration.c.id == 1)
        ).scalar_one_or_none()
        if raw is None:
            raise ControlError("controls_not_initialized", 503)
        return Policy.model_validate(raw)

    def _usage(self, conn: Connection, key: str, period: int) -> dict[str, int]:
        total = dict.fromkeys(UNITS, 0)
        # Old unresolved holds carry forward. Settled usage belongs to its
        # reservation period; it never silently moves to the response's period.
        rows = conn.execute(
            select(attempts).where(
                (attempts.c.period == period) | attempts.c.state.in_(["reserved", "unknown"])
            )
        ).mappings()
        for row in rows:
            if key in row["scopes"]:
                charge = row["actual"] if row["actual"] is not None else row["reserved"]
                for unit in UNITS:
                    total[unit] += charge[unit]
        return total

    def reserve(
        self, attempt_id: str, operation: str, scope: Scope, amount: Amount, kind: str
    ) -> dict:
        with self.transaction() as conn:
            return self.reserve_in(conn, attempt_id, operation, scope, amount, kind)

    def reserve_in(
        self,
        conn: Connection,
        attempt_id: str,
        operation: str,
        scope: Scope,
        amount: Amount,
        kind: str,
    ) -> dict:
        if kind not in {"model", "runner", "queue"} or not all(
            0 < len(s) <= 128 for s in (attempt_id, operation)
        ):
            raise ValueError("invalid attempt metadata")
        keys = list(scope.keys())
        old = conn.execute(select(attempts).where(attempts.c.id == attempt_id)).mappings().first()
        if old:
            if (old["operation"], old["scopes"], old["reserved"], old["kind"]) != (
                operation,
                keys,
                amount.model_dump(),
                kind,
            ):
                raise ControlError("attempt_conflict", 409)
            return dict(old)  # Replay is a lookup, never permission to execute again.
        policy = self.policy(conn)
        now = self.now(conn)
        period = int(now) // policy.period_seconds
        breaches = conn.execute(
            select(attempts.c.scopes).where(attempts.c.state == "overrun")
        ).scalars()
        if any(set(keys).intersection(scopes) for scopes in breaches):
            raise ControlError("unresolved_overrun", 503)
        for key, limits in zip(keys, policy.limits(), strict=True):
            usage = self._usage(conn, key, period)
            for unit, value in amount.model_dump().items():
                cap = getattr(limits, unit)
                if cap is not None and usage[unit] + value > cap:
                    raise ControlError("budget_exhausted")
        row = dict(
            id=attempt_id,
            operation=operation,
            scopes=keys,
            period=period,
            period_seconds=policy.period_seconds,
            policy=policy.model_dump(),
            kind=kind,
            reserved=amount.model_dump(),
            actual=None,
            state="reserved",
            created=now,
        )
        conn.execute(attempts.insert().values(**row))
        return row

    def settle(self, attempt_id: str, actual: Amount | None) -> None:
        with self.transaction() as conn:
            row = conn.execute(select(attempts).where(attempts.c.id == attempt_id)).mappings().one()
            value = actual.model_dump() if actual is not None else None
            if row["state"] in {"settled", "overrun"}:
                if row["actual"] != value:
                    raise ControlError("settlement_conflict", 409)
                return
            state = "unknown" if value is None else "settled"
            if value and any(value[u] > row["reserved"][u] for u in UNITS):
                state = "overrun"
            conn.execute(
                attempts.update()
                .where(attempts.c.id == attempt_id)
                .values(actual=value, state=state)
            )

    def summary(self) -> dict:
        with self.transaction() as conn:
            policy = self.policy(conn)
            rows = list(conn.execute(select(attempts)).mappings())
            return {
                "policy_version": policy.version,
                "currency": policy.currency,
                "attempts": len(rows),
                "states": {
                    s: sum(r["state"] == s for r in rows)
                    for s in ("reserved", "unknown", "settled", "overrun")
                },
                "reserved": {
                    u: sum(r["reserved"][u] for r in rows if r["actual"] is None) for u in UNITS
                },
                "consumed": {
                    u: sum(r["actual"][u] for r in rows if r["actual"] is not None) for u in UNITS
                },
            }
