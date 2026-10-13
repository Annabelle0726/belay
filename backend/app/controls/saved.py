# SPDX-License-Identifier: AGPL-3.0-only
"""Saved Ask links. Dialogue and coordinator MUST share one SQL transaction.

No copied history, second queue or cross-database atomicity assumption. The link
is content-free; the R2 turn is the sole durable released-dialogue record.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import Column, Integer, String, Table, inspect, select

from ..agent.reply_context import reply_metadata
from ..conversations.repository import ConversationStore
from .contracts import ControlError
from .ledger import metadata

links = Table(
    "control_conversations",
    metadata,
    Column("job", String(64), primary_key=True),
    Column("conversation", String(32), nullable=False, index=True),
    Column("revision", Integer, nullable=False),
    Column("policy", String(128), nullable=False),
)


def repository(store):
    injected = getattr(store, "dialogue", None)
    if injected is not None:
        if injected.engine.url != store.ledger.engine.url:
            raise ControlError("saved_database_mismatch", 503)
        return injected
    from ..config import settings
    from ..conversations.policy import Policy
    from ..store.db import engine

    def key(url):
        if url.get_backend_name() == "sqlite":
            return ("sqlite", str(Path(url.database or "").resolve()))
        return url

    if key(engine.url) != key(store.ledger.engine.url):
        raise ControlError("saved_database_mismatch", 503)
    return ConversationStore(store.ledger.engine, Policy.from_settings(settings))


def link(conn, job_id):
    return conn.execute(select(links).where(links.c.job == job_id)).mappings().first()


def check(store, conn, job_id, identity, *, reading=False):
    binding = link(conn, job_id)
    if binding is None:
        return None
    repo = repository(store)
    if binding["policy"] != repo.policy.policy_id:
        raise ControlError("conversation_unavailable", 404)
    try:
        result = repo.check_turn(
            identity,
            binding["conversation"],
            job_id,
            binding["revision"],
            conn,
            reading=reading,
        )
        if reading:
            from .admission import jobs

            state = conn.execute(select(jobs.c.state).where(jobs.c.id == job_id)).scalar_one()
            if state == "completed" and result["_turn_status"] != "completed":
                raise ControlError("publication_unavailable", 503)
        return result
    except HTTPException as exc:
        raise ControlError(
            "conversation_conflict" if exc.status_code == 409 else "conversation_unavailable",
            exc.status_code,
        ) from None


def submit(store, identity, cid, request_id, revision, payload, route):
    repo = repository(store)
    meta = repo.get(identity, cid)
    identity = replace(
        identity, exercise_id=meta["exercise_id"], exercise_version=meta["exercise_version"]
    )
    payload = {
        **payload,
        "participant_id": identity.learner_id,
        "exercise_id": identity.exercise_id,
    }
    job_id = store.job_id(identity, request_id)
    with store.ledger.transaction() as conn:
        previous = link(conn, job_id)
        if previous is None:
            try:
                repo.check_turn(identity, cid, job_id, revision, conn)
            except HTTPException as exc:
                raise ControlError(
                    "conversation_conflict"
                    if exc.status_code == 409
                    else "conversation_unavailable",
                    exc.status_code,
                ) from None
        elif (previous["conversation"], previous["revision"]) != (cid, revision):
            raise ControlError("operation_conflict", 409)
        # Route + target + revision are part of the immutable operation signature.
        result = store.submit(
            identity,
            request_id,
            payload,
            f"{route}:{cid}:{revision}",
            connection=conn,
            conversation_id=cid,
        )
        if previous is None:
            conn.execute(
                links.insert().values(
                    job=job_id, conversation=cid, revision=revision, policy=repo.policy.policy_id
                )
            )
        from .data import data

        conn.execute(
            data.update()
            .where(data.c.job == job_id, data.c.expires > meta["expires_at"])
            .values(expires=meta["expires_at"])
        )
        return result


def begin(store, job, identity, payload):
    with store.ledger.transaction() as conn:
        binding = link(conn, job["id"])
        if binding is None:
            return payload, None
        store.admission._live(conn, job["id"], job["fence"])
        check(store, conn, job["id"], identity)
        repo = repository(store)
        from ..conversations.bounds import recent_window
        from ..conversations.router import PLACEHOLDER

        message = payload.get("recent", [{}])[-1].get("text", "")
        replay = repo.begin(
            identity,
            binding["conversation"],
            job["id"],
            job["fingerprint"],
            binding["revision"],
            PLACEHOLDER if payload.get("_support") else message,
            connection=conn,
            reply_to=reply_metadata(payload["_reply_context"], payload["_reply_context"]["text"])
            if payload.get("_reply_context") and not payload.get("_support")
            else None,
        )
        if replay is not None:
            raise ControlError(
                "publication_unavailable", 503
            )  # Never infer an already completed turn again.
        # Completed history is fetched from R2, never supplied by the browser.
        recent = recent_window(
            repo.context(identity, binding["conversation"]),
            message,
            payload.pop("_persona"),
            repo.policy,
        )
        return {**payload, "recent": recent}, repo.policy


def complete(store, conn, job, identity, value):
    binding = link(conn, job["id"])
    if binding is None:
        return value
    check(store, conn, job["id"], identity)
    result = repository(store).complete(
        identity,
        binding["conversation"],
        job["id"],
        {"message": value["message"], "check_question": value.get("check_question")},
        connection=conn,
    )
    return {**value, "conversation_id": binding["conversation"], "revision": result["revision"]}


def erase_in(conn, cid):
    """Called by R2 delete/maintenance inside its own transaction. No refund."""
    if not inspect(conn).has_table(links.name):
        return
    from .data import data

    conn.execute(
        data.delete().where(data.c.job.in_(select(links.c.job).where(links.c.conversation == cid)))
    )


def cleanup_in(ledger, conn):
    rows = conn.execute(select(links)).mappings().all()
    if not rows:
        return
    from sqlalchemy import update

    from ..config import settings
    from ..conversations.ledger import DeletionLedger
    from ..conversations.models import Conversation, Turn
    from .admission import jobs
    from .data import data

    deleted = DeletionLedger(settings.dialogue_deletion_ledger_file).deleted()
    now = ledger.now(conn)
    for binding in rows:
        row = (
            conn.execute(
                select(Conversation.__table__).where(Conversation.id == binding["conversation"])
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row["deleted"]
            or row["expires_at"] <= now
            or binding["conversation"] in deleted
        ):
            conn.execute(data.delete().where(data.c.job == binding["job"]))
        else:
            state = conn.execute(
                select(jobs.c.state).where(jobs.c.id == binding["job"])
            ).scalar_one()
            if state in {"failed", "cancelled", "unknown"}:
                conn.execute(
                    update(Conversation)
                    .where(
                        Conversation.id == binding["conversation"],
                        Conversation.pending_id == binding["job"],
                    )
                    .values(pending_id=None, pending_until=0)
                )
                conn.execute(
                    update(Turn)
                    .where(
                        Turn.conversation_id == binding["conversation"],
                        Turn.request_id == binding["job"],
                        Turn.status == "pending",
                    )
                    .values(status="unknown" if state == "unknown" else "failed")
                )
