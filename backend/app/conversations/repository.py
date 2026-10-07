# SPDX-License-Identifier: AGPL-3.0-only
"""Short SQL transactions for scoped attempts and idempotent sequential turns."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from ..auth import Identity, denied
from .bounds import wire_size
from .models import Bucket, Conversation, Message, SchemaVersion, Turn
from .policy import Policy


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class ConversationStore:
    def __init__(self, engine, policy: Policy, clock: Callable[[], float] = time.time):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False)
        self.policy = policy
        self.clock = clock

    def _ready(self) -> None:
        self.policy.require()
        from sqlalchemy.exc import SQLAlchemyError

        try:
            with self.sessions() as session:
                version = session.get(SchemaVersion, "dialogue")
                if version is None or version.version != 1:
                    raise ValueError
        except (SQLAlchemyError, AttributeError, ValueError):
            raise HTTPException(503, "dialogue schema requires migration") from None

    def _owned(self, session: Session, identity: Identity, cid: str) -> Conversation:
        row = session.get(Conversation, cid)
        if (
            row is None
            or row.owner_key != identity.storage_id
            or row.deleted
            or row.expires_at <= int(self.clock())
            or row.policy_id != self.policy.policy_id
            or (row.exercise_id, row.exercise_version) not in identity.active_assignments
        ):
            raise denied()
        return row

    @staticmethod
    def metadata(row: Conversation) -> dict:
        return {
            "conversation_id": row.id,
            "attempt_id": row.id,
            "exercise_id": row.exercise_id,
            "exercise_version": row.exercise_version,
            "revision": row.revision,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "pending": row.pending_id is not None,
        }

    def create(self, identity: Identity, request_id: str) -> dict:
        self._ready()
        if (
            not identity.exercise_id
            or (identity.exercise_id, identity.exercise_version) not in identity.active_assignments
        ):
            raise denied()
        assignment = identity.exercise_key(identity.exercise_id, identity.exercise_version)
        cid = digest([identity.storage_id, assignment, request_id])[:32]
        with self.sessions.begin() as session:
            # Serialize creation per owner/assignment to make retained-attempt quotas atomic.
            bid = digest([identity.storage_id, assignment])
            factory = pg_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
            session.execute(
                factory(Bucket)
                .values(id=bid, revision=0)
                .on_conflict_do_nothing(index_elements=[Bucket.id])
            )
            session.execute(
                update(Bucket).where(Bucket.id == bid).values(revision=Bucket.revision + 1)
            )
            if session.get(Conversation, cid) is not None:
                return self.metadata(self._owned(session, identity, cid))
            count = session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.owner_key == identity.storage_id,
                    Conversation.assignment_key == assignment,
                    Conversation.deleted.is_(False),
                    Conversation.expires_at > int(self.clock()),
                )
            )
            if (count or 0) >= self.policy.max_attempts:
                raise HTTPException(409, "retained attempt limit reached; delete an attempt first")
            now = int(self.clock())
            row = Conversation(
                id=cid,
                owner_key=identity.storage_id,
                assignment_key=assignment,
                exercise_id=identity.exercise_id,
                exercise_version=identity.exercise_version,
                policy_id=self.policy.policy_id,
                created_at=now,
                expires_at=now + self.policy.retention_seconds,
            )
            session.add(row)
            session.flush()
            return self.metadata(row)

    def get(self, identity: Identity, cid: str) -> dict:
        self._ready()
        with self.sessions() as session:
            return self.metadata(self._owned(session, identity, cid))

    def attempts(self, identity: Identity, exercise_id: str, version: str) -> list[dict]:
        self._ready()
        if (exercise_id, version) not in identity.active_assignments:
            raise denied()
        with self.sessions() as session:
            rows = session.scalars(
                select(Conversation)
                .where(
                    Conversation.owner_key == identity.storage_id,
                    Conversation.exercise_id == exercise_id,
                    Conversation.exercise_version == version,
                    Conversation.deleted.is_(False),
                    Conversation.expires_at > int(self.clock()),
                    Conversation.policy_id == self.policy.policy_id,
                )
                .order_by(Conversation.created_at.desc(), Conversation.id)
                .limit(self.policy.max_attempts)
            )
            return [self.metadata(row) for row in rows]

    def history(self, identity: Identity, cid: str, before: str | None = None) -> dict:
        self._ready()
        with self.sessions() as session:
            row = self._owned(session, identity, cid)
            query = select(Message).where(Message.conversation_id == cid)
            if before is not None:
                try:
                    boundary, proof = before.split(".")
                    sequence = int(boundary)
                    if sequence < 1 or proof != digest([identity.storage_id, cid, sequence]):
                        raise ValueError
                except (ValueError, TypeError):
                    raise denied() from None
                query = query.where(Message.sequence < sequence)
            candidates = session.scalars(
                query.order_by(Message.sequence.desc()).limit(self.policy.page_messages + 1)
            ).all()
            page: list[dict] = []
            meta = self.metadata(row)
            for msg in candidates[: self.policy.page_messages]:
                turn = session.get(Turn, (cid, msg.request_id))
                status = turn.status if turn else "failed"
                if status == "pending" and row.pending_until <= int(self.clock()):
                    status = "failed"
                item = {
                    "sequence": msg.sequence,
                    "role": msg.role,
                    "text": msg.text,
                    "status": status,
                }
                trial = [item, *page]
                cursor: str | None = (
                    f"{msg.sequence}.{digest([identity.storage_id, cid, msg.sequence])}"
                )
                if (
                    wire_size({**meta, "messages": trial, "before": cursor})
                    > self.policy.page_bytes
                ):
                    break
                page = trial
            cursor = None
            if page and len(page) < len(candidates):
                sequence = page[0]["sequence"]
                cursor = f"{sequence}.{digest([identity.storage_id, cid, sequence])}"
            return {**meta, "messages": page, "before": cursor}

    def context(self, identity: Identity, cid: str) -> list[dict]:
        self._ready()
        with self.sessions() as session:
            self._owned(session, identity, cid)
            rows = session.scalars(
                select(Message)
                .join(
                    Turn,
                    (Message.conversation_id == Turn.conversation_id)
                    & (Message.request_id == Turn.request_id),
                )
                .where(Message.conversation_id == cid, Turn.status == "completed")
                .order_by(Message.sequence.desc())
                .limit(self.policy.max_messages)
            ).all()
            return [{"role": m.role, "text": m.text} for m in reversed(rows)]

    def begin(
        self,
        identity: Identity,
        cid: str,
        request_id: str,
        signature: str,
        expected_revision: int,
        learner_text: str,
    ) -> dict | None:
        self._ready()
        if len(learner_text.encode()) > self.policy.max_message_bytes:
            raise HTTPException(413, "message limit exceeded")
        with self.sessions.begin() as session:
            # UPDATE acquires a row lock on Postgres, and a write lock on SQLite.
            # No transaction spans a model call. Never update by an untrusted owner.
            session.execute(
                update(Conversation)
                .where(Conversation.id == cid, Conversation.owner_key == identity.storage_id)
                .values(revision=Conversation.revision)
            )
            row = self._owned(session, identity, cid)
            existing = session.get(Turn, (cid, request_id))
            if existing:
                if existing.digest != signature:
                    raise HTTPException(409, "request identifier reused with different input")
                if existing.status == "completed":
                    return dict(existing.response or {})
                if existing.status == "pending" and row.pending_until <= int(self.clock()):
                    existing.status = "failed"
                    row.pending_id = None
                    session.commit()
                raise HTTPException(409, "turn is pending or failed; refresh before a new request")
            if row.revision != expected_revision:
                raise HTTPException(409, "conversation changed; refresh history")
            if row.pending_id and row.pending_until > int(self.clock()):
                raise HTTPException(409, "another turn is pending")
            if row.pending_id:
                prior = session.get(Turn, (cid, row.pending_id))
                if prior:
                    prior.status = "failed"
            size = len(learner_text.encode())
            if (
                row.message_count + 2 > self.policy.max_messages
                or row.byte_count + size + self.policy.max_message_bytes * 7 + 1024
                > self.policy.max_stored_bytes
            ):
                raise HTTPException(409, "conversation storage limit reached; start a new attempt")
            row.revision += 1
            row.message_count += 1
            row.byte_count += size
            row.pending_id = request_id
            row.pending_until = int(self.clock()) + self.policy.pending_seconds
            session.add(
                Turn(conversation_id=cid, request_id=request_id, digest=signature, status="pending")
            )
            session.add(
                Message(
                    id=uuid.uuid4().hex,
                    conversation_id=cid,
                    request_id=request_id,
                    sequence=row.revision,
                    role="student",
                    text=learner_text,
                    byte_count=size,
                )
            )
        return None

    def complete(self, identity: Identity, cid: str, request_id: str, response: dict) -> dict:
        self._ready()
        message = response["message"]
        question = response.get("check_question")
        text = message + (("\n\n" + question) if question else "")
        if len(text.encode()) > self.policy.max_message_bytes:
            raise HTTPException(413, "released response exceeds saved message limit")
        with self.sessions.begin() as session:
            session.execute(
                update(Conversation)
                .where(Conversation.id == cid, Conversation.owner_key == identity.storage_id)
                .values(revision=Conversation.revision)
            )
            row = self._owned(session, identity, cid)
            if row.pending_id != request_id or row.pending_until <= int(self.clock()):
                raise HTTPException(409, "turn lease is no longer valid")
            turn = session.get(Turn, (cid, request_id))
            if turn is None:
                raise HTTPException(409, "turn lease is no longer valid")
            row.revision += 1
            row.message_count += 1

            row.pending_id = None
            turn.status = "completed"
            result = {
                "conversation_id": cid,
                "revision": row.revision,
                "response": {"message": message, "check_question": question},
            }
            retained_size = len(text.encode()) + wire_size(result)
            if row.byte_count + retained_size > self.policy.max_stored_bytes:
                raise HTTPException(409, "conversation storage limit reached")
            row.byte_count += retained_size
            turn.response = result
            session.add(
                Message(
                    id=uuid.uuid4().hex,
                    conversation_id=cid,
                    request_id=request_id,
                    sequence=row.revision,
                    role="assistant",
                    text=text,
                    byte_count=len(text.encode()),
                )
            )
            return result

    def fail(self, identity: Identity, cid: str, request_id: str) -> None:
        # Do not recreate a deleted or expired conversation on a late callback.
        with self.sessions.begin() as session:
            row = session.get(Conversation, cid)
            if row and row.owner_key == identity.storage_id and row.pending_id == request_id:
                row.pending_id = None
                turn = session.get(Turn, (cid, request_id))
                if turn:
                    turn.status = "failed"

    def delete(self, identity: Identity, cid: str) -> None:
        self._ready()
        with self.sessions.begin() as session:
            row = self._owned(session, identity, cid)
            row.deleted = True
            row.pending_id = None
            session.execute(delete(Message).where(Message.conversation_id == cid))
            session.execute(delete(Turn).where(Turn.conversation_id == cid))
