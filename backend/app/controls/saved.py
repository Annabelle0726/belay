# SPDX-License-Identifier: AGPL-3.0-only
"""Saved Ask links. Dialogue and coordinator MUST share one SQL transaction.

No copied history, second queue or cross-database atomicity assumption. The link
is content-free; the R2 turn is the sole durable released-dialogue record.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import Column, Integer, String, Table, select

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
        return repo.check_turn(
            identity,
            binding["conversation"],
            job_id,
            binding["revision"],
            conn,
            reading=reading,
        )
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
    job_id = store.job_id(identity, request_id)
    with store.ledger.transaction() as conn:
        previous = link(conn, job_id)
        if previous is None:
            repo.check_turn(identity, cid, job_id, revision, conn)
        elif (previous["conversation"], previous["revision"]) != (cid, revision):
            raise ControlError("operation_conflict", 409)
        # Route + target + revision are part of the immutable operation signature.
        result = store.submit(
            identity, request_id, payload, f"{route}:{cid}:{revision}", connection=conn
        )
        if previous is None:
            conn.execute(
                links.insert().values(
                    job=job_id, conversation=cid, revision=revision, policy=repo.policy.policy_id
                )
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
        repo.begin(
            identity,
            binding["conversation"],
            job["id"],
            job["fingerprint"],
            binding["revision"],
            PLACEHOLDER if payload.get("_support") else message,
            connection=conn,
        )
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
