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
from fastapi import HTTPException
from sqlalchemy import Column, Float, Integer, String, Table, Text, func, select
from sqlalchemy.engine import Connection

from ..agent.context import _latest_student_message
from ..agent.distress import extra_terms, frame_from_settings, has_distress_signal
from ..agent.glass_box import student_glass_box
from ..agent.reply_context import reply_metadata
from ..auth import (
    ExecutionGrant,
    Identity,
    capture_assignment_access,
    execution_grant,
    recheck_grant,
)
from ..config import settings
from ..integrations.quad.pii import PIIRejected, assert_no_pii
from ..schemas import SolTurnResponse
from . import saved
from .admission import Admission, jobs
from .contracts import Amount, ControlError, Scope
from .ledger import Ledger, attempts, metadata

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

    def _grant(self, conn: Connection, job_id: str, *, tutoring: bool = False) -> ExecutionGrant:
        raw = conn.execute(
            select(bindings.c.grant).where(bindings.c.id == job_id)
        ).scalar_one_or_none()
        if raw is None:
            raise ControlError("job_unavailable", 404)
        try:
            grant = ExecutionGrant.model_validate_json(raw)
            if tutoring and grant.purpose != "tutor":
                raise ControlError("job_unavailable", 404)
            return grant
        except ValueError:
            raise ControlError("job_unavailable", 404) from None

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
        conversation_id: str | None = None,
    ) -> dict:
        grant = execution_grant(
            identity, payload.get("mode", "study"), payload.get("stance", "peer")
        )
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
                if existing["reason"] == "request_not_admitted":
                    raise ControlError("request_not_admitted", 409)
                saved.check(self, conn, job_id, identity, reading=True)
                if existing["fingerprint"] != fingerprint:
                    raise ControlError("operation_conflict", 409)
                return self.admission._public(dict(existing))
            if stored.get("reply_to"):
                self.resolve_reply(conn, identity, stored["reply_to"], conversation_id)
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

    def resolve_reply(
        self, conn, identity: Identity, reference: dict, conversation_id=None
    ) -> dict:
        try:
            cid = reference.get("conversation_id")
            # Do not copy a saved reply into a different retention/deletion scope.
            if cid != conversation_id:
                raise ControlError("reply_unavailable", 409)
            if cid:
                return dict(
                    saved.repository(self).reply(
                        identity, cid, reference["request_id"], connection=conn
                    )
                )
            original_id = self.job_id(identity, reference["request_id"])
            grant = self._owned(conn, original_id, identity)
            if (grant.exercise_id, grant.exercise_version) != (
                identity.exercise_id,
                identity.exercise_version,
            ):
                raise ControlError("reply_unavailable", 409)
            original = (
                conn.execute(select(jobs).where(jobs.c.id == original_id)).mappings().one_or_none()
            )
            if (
                original is None
                or original["state"] != "completed"
                or saved.link(conn, original_id)
            ):
                raise ControlError("reply_unavailable", 409)
            value = self._get(conn, original_id, original["result_ref"], "result")
            if value.get("unsaved_exchange"):
                raise ControlError("reply_unavailable", 409)
            text = value["message"] + (
                "\n\n" + value["check_question"] if value.get("check_question") else ""
            )
            return {
                **reply_metadata(reference, text),
                "text": text,
                "original_evidence": value.get("glass_box"),
            }
        except (ControlError, HTTPException):
            raise ControlError("reply_unavailable", 409) from None

    def load(self, job: dict) -> tuple[Identity, dict]:
        with self.ledger.transaction() as conn:
            identity = recheck_grant(self._grant(conn, job["id"], tutoring=True))
            saved.check(self, conn, job["id"], identity)
            payload = self._get(conn, job["id"], job["payload_ref"], "input")
            if payload.get("reply_to"):
                binding = saved.link(conn, job["id"])
                payload["_reply_context"] = self.resolve_reply(
                    conn,
                    identity,
                    payload["reply_to"],
                    binding["conversation"] if binding else None,
                )
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
            identity = recheck_grant(self._grant(conn, job["id"], tutoring=True))
            conversation = saved.check(self, conn, job["id"], identity)
            payload = self._get(conn, job["id"], job["payload_ref"], "input")
            value = {
                "message": value["message"],
                "check_question": value.get("check_question"),
                "glass_box": student_glass_box(response, payload),
            }
            if payload.get("reply_to"):
                binding = saved.link(conn, job["id"])
                quote = self.resolve_reply(
                    conn,
                    identity,
                    payload["reply_to"],
                    binding["conversation"] if binding else None,
                )
                value["reply_to"] = reply_metadata(quote, quote["text"])
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
                    **(
                        {}
                        if screened or not value.get("reply_to")
                        else {"reply_to": value["reply_to"]}
                    ),
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
            identity = recheck_grant(self._grant(conn, job["id"], tutoring=True))
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

    def reconcile_missing(self, identity: Identity, request_id: str) -> dict:
        """Fence an absent unsaved request, never cancel or refund existing work.

        The same coordinator lock serializes this with admission. GET absence
        alone is not proof: the retained tombstone also rejects a delayed POST.
        No learner content, model calls or budget reservations are created.
        """
        grant = capture_assignment_access(identity, "recovery_fence")
        job_id = self.job_id(identity, request_id)
        with self.ledger.transaction() as conn:
            recheck_grant(grant)
            self.ledger.policy(conn)
            row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().first()
            if row is not None:
                self._owned(conn, job_id, identity)
                # This endpoint cannot recover a saved conversation through an
                # unsaved URL, or reveal another original subject's request.
                if saved.link(conn, job_id):
                    raise ControlError("job_unavailable", 404)
            else:
                evidence = (
                    conn.execute(select(bindings.c.id).where(bindings.c.id == job_id)).first()
                    or conn.execute(select(data.c.id).where(data.c.job == job_id)).first()
                    or conn.execute(
                        select(attempts.c.id).where(
                            (attempts.c.operation == job_id) | (attempts.c.id == "queue:" + job_id)
                        )
                    ).first()
                    or saved.link(conn, job_id)
                )
                if evidence:
                    raise ControlError("execution_unknown", 409)
                now = self.ledger.now(conn)
                conn.execute(bindings.insert().values(id=job_id, grant=grant.model_dump_json()))
                conn.execute(
                    jobs.insert().values(
                        id=job_id,
                        operation=request_id,
                        scopes=list(self.scope(identity).keys()),
                        fingerprint=hashlib.sha256(("not-admitted:" + job_id).encode()).hexdigest(),
                        payload_ref=None,
                        payload_bytes=0,
                        result_ref=None,
                        state="failed",
                        reason="request_not_admitted",
                        created=now,
                        expires=now,
                        lease=None,
                        deadline=None,
                        fence=0,
                        last_poll=None,
                        sequence=(conn.execute(select(func.max(jobs.c.sequence))).scalar() or 0)
                        + 1,
                    )
                )
            if row is None or row["reason"] == "request_not_admitted":
                return {
                    "id": job_id,
                    "state": "failed",
                    "reason": "request_not_admitted",
                    "result": None,
                }
        return self.status(identity, job_id)

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
