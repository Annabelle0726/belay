# SPDX-License-Identifier: AGPL-3.0-only
"""Expiry, physical deletion and recovery fences using temporary real databases."""

from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select

from app.conversations.models import Message, Turn
from app.conversations.repository import ConversationStore
from tests.test_conversations import dialogue as dialogue_fixture

dialogue = dialogue_fixture


def saved(store, owner):
    cid = store.create(owner, "one")["conversation_id"]
    store.begin(owner, cid, "one", "hash", 0, "hello")
    store.complete(owner, cid, "one", {"message": "released"})
    return cid


def test_expiry_hides_all_access_before_cleanup_and_cleanup_is_repeatable(dialogue):
    store, owner, now = dialogue
    cid = saved(store, owner)
    now[0] = 1300
    for operation in [
        lambda: store.get(owner, cid),
        lambda: store.history(owner, cid),
        lambda: store.context(owner, cid),
        lambda: store.begin(owner, cid, "two", "hash", 2, "hello"),
        lambda: store.complete(owner, cid, "one", {"message": "late"}),
        lambda: store.create(owner, "one"),
    ]:
        with pytest.raises(HTTPException) as exc:
            operation()
        assert exc.value.status_code == 404
    assert store.attempts(owner, "echo-1", "v1") == []
    assert store.cleanup() == 1
    assert store.cleanup() == 0
    with store.sessions() as session:
        assert session.scalars(select(Message)).all() == []
        assert session.scalars(select(Turn)).all() == []


def test_deleted_attempt_cannot_complete_or_retry(dialogue):
    store, owner, _ = dialogue
    cid = store.create(owner, "one")["conversation_id"]
    store.begin(owner, cid, "one", "hash", 0, "hello")
    store.delete(owner, cid)
    with pytest.raises(HTTPException) as exc:
        store.complete(owner, cid, "one", {"message": "late result"})
    assert exc.value.status_code == 404
    store.fail(owner, cid, "one")
    assert cid in store.ledger.deleted()
    assert store.cleanup() == 0
    with store.sessions() as session:
        assert session.scalars(select(Message)).all() == []
        assert session.scalars(select(Turn)).all() == []
    with pytest.raises(HTTPException):
        store.create(owner, "one")


def test_old_backup_stays_inaccessible_and_is_physically_cleaned(dialogue, tmp_path):
    import sqlite3

    store, owner, _ = dialogue
    cid = saved(store, owner)
    backup_path = str(tmp_path / "restored.db")
    with store.engine.connect() as connection, sqlite3.connect(backup_path) as backup:
        connection.connection.driver_connection.backup(backup)
    store.delete(owner, cid)
    restored_engine = create_engine("sqlite:///" + backup_path)
    restored = ConversationStore(restored_engine, store.policy, store.clock)
    try:
        with pytest.raises(HTTPException) as exc:
            restored.history(owner, cid)
        assert exc.value.status_code == 404
        assert restored.attempts(owner, "echo-1", "v1") == []
        with pytest.raises(HTTPException):
            restored.create(owner, "one")
        assert restored.cleanup() == 1
        assert restored.cleanup() == 0
        with restored.sessions() as session:
            assert session.scalars(select(Message)).all() == []
            assert session.scalars(select(Turn)).all() == []
    finally:
        restored_engine.dispose()


def test_missing_or_corrupt_ledger_fails_closed(dialogue, tmp_path):
    store, owner, _ = dialogue
    missing = replace(store.policy, deletion_ledger_file=str(tmp_path / "missing"))
    with pytest.raises(HTTPException) as exc:
        ConversationStore(store.engine, missing).create(owner, "one")
    assert exc.value.status_code == 503
    store.ledger.path.write_text('{"schema":1}\n{"conversation_id":')
    with pytest.raises(HTTPException) as exc:
        store.create(owner, "one")
    assert exc.value.status_code == 503
