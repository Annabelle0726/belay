# SPDX-License-Identifier: AGPL-3.0-only
"""Offline ownership, repeatable migration and transactional storage contract."""

from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select

from app.auth import AssignmentGrant, Identity, behavior_receipt
from app.conversations.ledger import DeletionLedger
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
    DeletionLedger(policy.deletion_ledger_file).initialize()
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


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("change", ["narrow", "regrant", "legacy"])
def test_history_quotes_recheck_original_permission_without_assistant_on_page(
    dialogue, pending, change
):
    store, owner, _ = dialogue
    store.policy = replace(store.policy, page_messages=1)
    grant = AssignmentGrant(
        version="v1",
        generation="grant-1",
        policy_revision=1,
        allowed_pairs=[{"mode": "study", "stance": "peer"}, {"mode": "teach", "stance": "oracle"}],
    )
    owner = replace(
        owner,
        subject="subject-a",
        issuer="https://issuer.invalid",
        audience="test",
        assignment_policies=(("echo-1", grant),),
    )
    cid = store.create(owner, "create-quote")["conversation_id"]
    store.begin(owner, cid, "oracle-1", "original", 0, "Explain")
    store.complete(
        owner,
        cid,
        "oracle-1",
        {"message": "PROTECTED_ORACLE_ANSWER"},
        authorization=behavior_receipt(owner, "teach", "oracle"),
    )
    reply = store.reply(owner, cid, "oracle-1")
    quote = {key: reply[key] for key in ("request_id", "conversation_id", "excerpt")}
    store.begin(owner, cid, "followup-1", "followup", 2, "Why?", reply_to=quote)
    if not pending:
        store.fail(owner, cid, "followup-1")
    page = store.history(owner, cid)
    assert len(page["messages"]) == 1
    assert page["messages"][0]["role"] == "student"
    assert page["messages"][0]["reply_to"]["excerpt"] == "PROTECTED_ORACLE_ANSWER"
    if change == "legacy":
        with store.sessions.begin() as session:
            original = session.get(Turn, (cid, "oracle-1"))
            original.response = {"message": "PROTECTED_ORACLE_ANSWER"}
        fresh = owner
    else:
        fresh = replace(
            owner,
            assignment_policies=(
                (
                    "echo-1",
                    grant.model_copy(update={"generation": "grant-2"})
                    if change == "regrant"
                    else AssignmentGrant(
                        **{
                            **grant.model_dump(),
                            "policy_revision": 2,
                            "allowed_pairs": [{"mode": "study", "stance": "peer"}],
                        }
                    ),
                ),
            ),
        )
    with pytest.raises(HTTPException) as direct:
        store.reply(fresh, cid, "oracle-1")
    assert direct.value.status_code == 404
    with pytest.raises(HTTPException) as history:
        store.history(fresh, cid)
    assert history.value.status_code == 404


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
    assert [m["request_id"] for m in page["messages"]] == ["turn-1", "turn-1"]
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


def test_concurrent_turns_have_one_winner(dialogue):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store, owner, _ = dialogue
    cid = store.create(owner, "one")["conversation_id"]
    barrier = Barrier(2)

    def attempt(request_id):
        barrier.wait()
        try:
            store.begin(owner, cid, request_id, request_id, 0, "hello")
            return 200
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(attempt, ["one", "two"])) == [200, 409]
    assert len(store.history(owner, cid)["messages"]) == 1
