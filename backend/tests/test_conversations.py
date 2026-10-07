# SPDX-License-Identifier: AGPL-3.0-only
"""Offline ownership, repeatable migration and transactional storage contract."""

from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select

from app.auth import Identity
from app.conversations.migration import migrate
from app.conversations.models import Message, Turn
from app.conversations.policy import Policy
from app.conversations.repository import ConversationStore
from app.store.models import Base


@pytest.fixture
def dialogue(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "dialogue.db"))
    Base.metadata.create_all(engine)
    migrate(engine)
    migrate(engine)
    now = [1000]
    policy = Policy(
        enabled=True,
        policy_id="local-review",
        retention_seconds=300,
        backup_max_age_seconds=300,
        deletion_ledger_file=str(tmp_path / "deletions.jsonl"),
    )
    owner = Identity(
        "inst-a", "class-a", "gh:1", (("echo-1", "v1"),), "echo-1", "v1", (("echo-1", "v1"),)
    )
    store = ConversationStore(engine, policy, lambda: now[0])
    yield store, owner, now
    engine.dispose()


def test_migration_is_additive_and_repeatable(dialogue):
    store, _, _ = dialogue
    assert {"participants", "events", "conversations", "conversation_messages"} <= set(
        inspect(store.engine).get_table_names()
    )
    with store.sessions() as session:
        assert session.scalars(select(Message)).all() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("institution_id", "inst-b"),
        ("class_id", "class-b"),
        ("learner_id", "gh:2"),
        ("active_assignments", (("echo-1", "v2"),)),
    ],
)
def test_all_operations_share_owner_and_version_boundary(dialogue, field, value):
    store, owner, _ = dialogue
    cid = store.create(owner, "create-1")["conversation_id"]
    other = replace(owner, **{field: value})
    for action in [
        lambda: store.get(other, cid),
        lambda: store.history(other, cid),
        lambda: store.begin(other, cid, "turn-1", "hash", 0, "hello"),
        lambda: store.complete(other, cid, "turn-1", {"message": "hello"}),
        lambda: store.delete(other, cid),
    ]:
        with pytest.raises(HTTPException) as exc:
            action()
        assert exc.value.status_code == 404
    assert store.get(owner, cid)["revision"] == 0


def test_sequencing_retry_and_restarted_store(dialogue):
    store, owner, _ = dialogue
    cid = store.create(owner, "create-1")["conversation_id"]
    assert store.create(owner, "create-1")["conversation_id"] == cid
    assert store.begin(owner, cid, "turn-1", "hash", 0, "hello") is None
    with pytest.raises(HTTPException) as exc:
        store.begin(owner, cid, "turn-2", "other", 1, "second")
    assert exc.value.status_code == 409
    response = store.complete(
        owner, cid, "turn-1", {"message": "released", "check_question": "why?", "planner": "secret"}
    )
    reopened = ConversationStore(store.engine, store.policy, store.clock)
    assert reopened.begin(owner, cid, "turn-1", "hash", 0, "hello") == response
    page = reopened.history(owner, cid)
    assert [m["role"] for m in page["messages"]] == ["student", "assistant"]
    assert "secret" not in str(page)
    with store.sessions() as session:
        assert session.get(Turn, (cid, "turn-1")).response == response


def test_failures_and_expired_leases_are_visible(dialogue):
    store, owner, now = dialogue
    cid = store.create(owner, "create-1")["conversation_id"]
    store.begin(owner, cid, "one", "hash", 0, "hello")
    now[0] += 121
    with pytest.raises(HTTPException):
        store.begin(owner, cid, "one", "hash", 0, "hello")
    assert store.history(owner, cid)["messages"][0]["status"] == "failed"
    store.begin(owner, cid, "two", "hash", 1, "retry with new request")
    store.fail(owner, cid, "two")
    assert store.history(owner, cid)["messages"][-1]["status"] == "failed"
