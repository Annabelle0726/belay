# SPDX-License-Identifier: AGPL-3.0-only
"""The external coordinator transaction owns dialogue commit and rollback."""

import pytest
from sqlalchemy import select

from app.controls.ledger import Ledger
from app.conversations.models import Message, Turn
from tests.test_conversations import dialogue  # noqa: F401


def test_dialogue_can_join_coordinator_commit_and_idempotent_complete(dialogue):  # noqa: F811
    repo, identity, _ = dialogue
    cid = repo.create(identity, "create")["conversation_id"]
    ledger = Ledger(repo.engine)
    with ledger.transaction() as conn:
        repo.check_turn(identity, cid, "operation", 0, conn)
        repo.begin(identity, cid, "operation", "signature", 0, "Question", connection=conn)
        repo.check_turn(identity, cid, "operation", 0, conn)
        result = repo.complete(identity, cid, "operation", {"message": "Answer"}, connection=conn)
        assert (
            repo.complete(identity, cid, "operation", {"message": "Answer"}, connection=conn)
            == result
        )
    assert repo.get(identity, cid)["revision"] == 2
    with repo.sessions() as session:
        assert len(session.scalars(select(Message)).all()) == 2


def test_dialogue_completion_rolls_back_with_outer_transaction(dialogue):  # noqa: F811
    repo, identity, _ = dialogue
    cid = repo.create(identity, "create")["conversation_id"]
    repo.begin(identity, cid, "operation", "signature", 0, "Question")
    with pytest.raises(RuntimeError):
        with Ledger(repo.engine).transaction() as conn:
            repo.complete(identity, cid, "operation", {"message": "Answer"}, connection=conn)
            raise RuntimeError("crash before SQL commit")
    assert repo.get(identity, cid)["revision"] == 1
    with repo.sessions() as session:
        assert session.get(Turn, (cid, "operation")).status == "pending"
        assert len(session.scalars(select(Message)).all()) == 1
