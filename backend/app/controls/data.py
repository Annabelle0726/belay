# SPDX-License-Identifier: AGPL-3.0-only
"""Short-lived encrypted execution data, separate from research and accounting.

Only operator initialization/migration creates these tables. The same coordinator
transaction owns admission/data insertion and result publication/completion.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import nullcontext

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Column, Float, Integer, String, Table, Text, select
from sqlalchemy.engine import Connection

from ..agent.context import _latest_student_message
from ..agent.distress import extra_terms, frame_from_settings, has_distress_signal
from ..agent.glass_box import student_glass_box
from ..auth import ExecutionGrant, Identity, execution_grant, recheck_grant
from ..config import settings
from ..integrations.quad.pii import PIIRejected, assert_no_pii
from ..schemas import SolTurnResponse
from . import saved
from .admission import Admission, jobs
from .contracts import Amount, ControlError, Scope
from .ledger import Ledger, metadata

bindings = Table(
    "control_bindings",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("grant", Text, nullable=False),  # pseudonymous scope + opaque principal ref only
)
data = Table(
    "control_data",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("job", String(64), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("body", Text, nullable=False),
    Column("bytes", Integer, nullable=False),
    Column("expires", Float, nullable=False, index=True),
)


class ExecutionData:
    def __init__(self, ledger: Ledger, deployment: str, key: bytes):
        if not deployment or len(deployment) > 128:
            raise ValueError("stable deployment ID required")
        self.ledger, self.deployment = ledger, deployment
        self.admission = Admission(ledger)
        self.cipher = Fernet(key)

    def scope(self, identity: Identity) -> Scope:
        return Scope(
            self.deployment, identity.institution_id, identity.class_id, identity.learner_id
        )

    def job_id(self, identity: Identity, request_id: str) -> str:
        return hashlib.sha256(
            (self.scope(identity).keys()[-1] + ":" + request_id).encode()
        ).hexdigest()

    def _grant(self, conn: Connection, job_id: str) -> ExecutionGrant:
        raw = conn.execute(
            select(bindings.c.grant).where(bindings.c.id == job_id)
        ).scalar_one_or_none()
        if raw is None:
            raise ControlError("job_unavailable", 404)
        return ExecutionGrant.model_validate_json(raw)

    def _owned(self, conn: Connection, job_id: str, identity: Identity) -> ExecutionGrant:
        grant = self._grant(conn, job_id)
        if grant.grant_ref != identity.grant_ref or (
            grant.institution_id,
            grant.class_id,
            grant.learner_id,
        ) != (identity.institution_id, identity.class_id, identity.learner_id):
            raise ControlError("job_unavailable", 404)
        recheck_grant(grant)
        return grant

    def _put(self, conn: Connection, job_id: str, kind: str, body: dict, expires: float) -> str:
        try:
            raw = json.dumps(
                body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode()
        except (ValueError, TypeError):
            raise ControlError("invalid_execution_data", 422) from None
        policy = self.ledger.policy(conn)
        if len(raw) > policy.payload_bytes:
            raise ControlError("payload_too_large", 413)
        ref = uuid.uuid4().hex
        conn.execute(
            data.insert().values(
                id=ref,
                job=job_id,
                kind=kind,
                body=self.cipher.encrypt(raw).decode(),
                bytes=len(raw),
                expires=expires,
            )
        )
        return ref

    def _get(self, conn: Connection, job_id: str, ref: str | None, kind: str) -> dict:
        row = (
            conn.execute(
                select(data).where(data.c.id == ref, data.c.job == job_id, data.c.kind == kind)
            )
            .mappings()
            .first()
        )
        if row is None or row["expires"] <= self.ledger.now(conn):
            raise ControlError(
                "result_expired" if kind in {"result", "pending"} else "input_expired", 410
            )
        try:
            value = dict(json.loads(self.cipher.decrypt(row["body"].encode())))
            if kind == "result" and value.pop("_support_result", False):
                # Institution-configured support resources are rendered live, not
                # persisted as learner content. No distressing utterance is retained.
                value["message"] = frame_from_settings(settings)
            return value
        except (InvalidToken, ValueError, TypeError):
            raise ControlError("execution_data_unavailable", 503) from None

    def cleanup_in(self, conn: Connection) -> int:
        """Physical deletion; expiry is also checked on every read/publication.

        Terminal input/pending content is deleted promptly; unknown attempts and
        content-free dedup/authorization tombstones are never refunded/deleted here.
        """
        return cleanup_in(self.ledger, conn)

    def cleanup(self) -> int:
        with self.ledger.transaction() as conn:
            return self.cleanup_in(conn)

    def submit(
        self,
        identity: Identity,
        request_id: str,
        payload: dict,
        route: str,
        *,
        connection: Connection | None = None,
    ) -> dict:
        grant = execution_grant(identity)
        stored = temporary_input(payload)
        recheck_grant(grant)
        raw = json.dumps(
            [route, grant.model_dump(), payload], sort_keys=True, separators=(",", ":")
        )
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        job_id = self.job_id(identity, request_id)
        with (
            nullcontext(connection) if connection is not None else self.ledger.transaction()
        ) as conn:
            self.cleanup_in(conn)
            existing = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
            if existing:
                self._owned(conn, job_id, identity)
                saved.check(self, conn, job_id, identity, reading=True)
                if existing["fingerprint"] != fingerprint:
                    raise ControlError("operation_conflict", 409)
                return self.admission._public(dict(existing))
            policy = self.ledger.policy(conn)
            now = self.ledger.now(conn)
            ref = self._put(
                conn,
                job_id,
                "input",
                stored,
                now + policy.queue_wait_seconds + policy.execution_seconds,
            )
            conn.execute(bindings.insert().values(id=job_id, grant=grant.model_dump_json()))
            return self.admission.submit(
                self.scope(identity),
                request_id,
                fingerprint,
                ref,
                len(json.dumps(payload).encode()),
                Amount(),
                connection=conn,
            )

    def load(self, job: dict) -> tuple[Identity, dict]:
        with self.ledger.transaction() as conn:
            identity = recheck_grant(self._grant(conn, job["id"]))
            saved.check(self, conn, job["id"], identity)
            payload = self._get(conn, job["id"], job["payload_ref"], "input")
            return identity, payload

    def stage(self, job: dict, response: dict) -> str:
        value = SolTurnResponse.model_validate(response).model_dump()
        try:
            json.dumps(value, allow_nan=False)
        except (ValueError, TypeError):
            raise ControlError("invalid_execution_data", 422) from None
        if not value["message"].strip():
            raise ControlError("invalid_result", 502)
        with self.ledger.transaction() as conn:
            self.admission._live(conn, job["id"], job["fence"])
            identity = recheck_grant(self._grant(conn, job["id"]))
            conversation = saved.check(self, conn, job["id"], identity)
            payload = self._get(conn, job["id"], job["payload_ref"], "input")
            value = {
                "message": value["message"],
                "check_question": value.get("check_question"),
                "glass_box": student_glass_box(response, payload),
            }
            if payload.get("_support"):
                value = {**value, "_support_result": True, "message": "Support response available."}
            if conversation is not None:
                from ..conversations.router import PLACEHOLDER, private_content

                screened = payload.get("_support") or private_content(
                    value["message"] + (value.get("check_question") or "")
                )
                value = {
                    "message": PLACEHOLDER if screened else value["message"],
                    "check_question": None if screened else value.get("check_question"),
                    **({} if screened else {"glass_box": value["glass_box"]}),
                }
                if payload.get("_support"):
                    value["_support_result"] = True
                    value["unsaved_exchange"] = True
            require_storable(value)
            expires = self.ledger.now(conn) + self.ledger.policy(conn).result_seconds
            if conversation is not None:
                expires = min(expires, conversation["expires_at"])
            return self._put(
                conn,
                job["id"],
                "pending",
                value,
                expires,
            )

    def publish(self, job: dict, ref: str) -> None:
        with self.ledger.transaction() as conn:
            self.admission._live(conn, job["id"], job["fence"])
            identity = recheck_grant(self._grant(conn, job["id"]))
            saved.check(self, conn, job["id"], identity)
            self._get(conn, job["id"], job["payload_ref"], "input")
            value = self._get(conn, job["id"], ref, "pending")
            if not isinstance(value.get("message"), str) or not value["message"].strip():
                raise ControlError("invalid_result", 502)
            value = saved.complete(self, conn, job, identity, value)
            require_storable(value)
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            if len(raw) > self.ledger.policy(conn).payload_bytes:
                raise ControlError("payload_too_large", 413)
            conn.execute(
                data.update()
                .where(data.c.id == ref)
                .values(kind="result", body=self.cipher.encrypt(raw).decode(), bytes=len(raw))
            )
            self.admission.finish(job["id"], job["fence"], ref, authorized=True, connection=conn)
            self.cleanup_in(conn)

    def status(self, identity: Identity, job_id: str) -> dict:
        # Authorization precedes rate-limited status; a different principal cannot
        # consume the original owner's polling window or learn its state.
        with self.ledger.transaction() as conn:
            self._owned(conn, job_id, identity)
            saved.check(self, conn, job_id, identity, reading=True)
        status = self.admission.status(self.scope(identity), job_id)
        with self.ledger.transaction() as conn:
            self._owned(conn, job_id, identity)
            saved.check(self, conn, job_id, identity, reading=True)
            self.cleanup_in(conn)
            response = None
            if status["state"] == "completed":
                try:
                    response = self._get(conn, job_id, status["result_ref"], "result")
                except ControlError as exc:
                    if exc.code != "result_expired":
                        raise
                    status = status | {"state": "result_expired", "reason": "result_expired"}
            return {
                "id": job_id,
                "state": status["state"],
                "reason": status["reason"],
                "result": response,
                "poll_seconds": self.ledger.policy(conn).poll_seconds,
            }


def require_storable(value: dict) -> None:
    # Operational recovery has stricter storage requirements than source execution:
    # source exemptions must not persist contact information or distress verbatim.
    text = json.dumps(value, ensure_ascii=False)
    try:
        assert_no_pii(value)
        assert_no_pii({"content": text})
    except PIIRejected:
        raise ControlError("content_not_storable", 422) from None
    if has_distress_signal(text, extra_terms(settings)):
        raise ControlError("content_not_storable", 422)


def temporary_input(payload: dict) -> dict:
    latest = _latest_student_message(payload.get("recent", []))
    if settings.distress_routing_enabled and has_distress_signal(latest, extra_terms(settings)):
        # Preserve the existing deterministic support path without retaining the
        # distressing source/history or category. No model sees this content.
        return {
            "_support": True,
            **{
                k: payload[k]
                for k in ("participant_id", "exercise_id", "event", "mode", "stance")
                if k in payload
            },
        }
    require_storable(payload)
    return payload


def cleanup_in(ledger: Ledger, conn: Connection) -> int:
    saved.cleanup_in(ledger, conn)
    now = ledger.now(conn)
    Admission(ledger)._expire(conn, now)
    terminal = select(jobs.c.id).where(jobs.c.state.not_in(["queued", "running"]))
    rows = conn.execute(
        data.delete().where(
            (data.c.expires <= now) | ((data.c.kind != "result") & data.c.job.in_(terminal))
        )
    )
    return int(rows.rowcount)
