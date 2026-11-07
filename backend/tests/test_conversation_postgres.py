# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in real PostgreSQL checks in an isolated disposable schema; never a model service."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text

from app.auth import Identity
from app.conversations.ledger import DeletionLedger
from app.conversations.migration import migrate
from app.conversations.models import Message
from app.conversations.policy import Policy
from app.conversations.repository import ConversationStore
from app.store.models import Event, LearnerState, Participant


@pytest.mark.skipif(
    not os.environ.get("TEST_DIALOGUE_POSTGRES_URL"),
    reason="disposable PostgreSQL DSN not configured",
)
def test_postgres_migration_existing_data_retry_and_concurrency(tmp_path):
    url = os.environ["TEST_DIALOGUE_POSTGRES_URL"]
    schema = "belay_r2_" + uuid.uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={schema}"}, hide_parameters=True
    )
    try:
        with engine.begin() as connection:
            for model in [Participant, LearnerState, Event]:
                model.__table__.create(connection)
            connection.execute(
                Participant.__table__.insert().values(id="legacy", anon_code="legacy", consent=True)
            )
            connection.execute(
                Event.__table__.insert().values(
                    participant_id="legacy",
                    exercise_id="echo-1",
                    mode="study",
                    event_type="turn",
                    payload={"message": "legacy trace"},
                )
            )
        migrate(engine)
        migrate(engine)
        policy = Policy(
            enabled=True,
            policy_id="pg-local",
            retention_seconds=300,
            backup_max_age_seconds=300,
            deletion_ledger_file=str(tmp_path / "deletions.jsonl"),
            max_attempts=1,
        )
        DeletionLedger(policy.deletion_ledger_file).initialize()
        owner = Identity(
            "inst", "class", "gh:1", (("echo-1", "v1"),), "echo-1", "v1", (("echo-1", "v1"),)
        )
        store = ConversationStore(engine, policy, lambda: 1000)
        with store.sessions() as session:
            assert session.scalars(select(Message)).all() == []
            assert len(session.scalars(select(Event)).all()) == 1
        barrier = Barrier(2)

        def create_attempt(request):
            barrier.wait()
            try:
                return store.create(owner, request)["conversation_id"]
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(create_attempt, ["one", "two"]))
        assert results.count(409) == 1
        cid = next(result for result in results if isinstance(result, str))
        barrier = Barrier(2)

        def begin_turn(request):
            barrier.wait()
            try:
                store.begin(owner, cid, request, request, 0, "hello")
                return request
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(begin_turn, ["one", "two"]))
        assert results.count(409) == 1
        request = next(result for result in results if isinstance(result, str))
        response = store.complete(owner, cid, request, {"message": "released"})
        restarted = ConversationStore(engine, policy, lambda: 1000)
        assert restarted.begin(owner, cid, request, request, 0, "hello") == response
        assert len(restarted.history(owner, cid)["messages"]) == 2
        with pytest.raises(HTTPException):
            restarted.history(replace(owner, class_id="other"), cid)
        restarted.delete(owner, cid)
        with pytest.raises(HTTPException):
            store.complete(owner, cid, request, {"message": "late"})
        assert store.cleanup() == 0
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()
