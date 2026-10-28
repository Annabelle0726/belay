# SPDX-License-Identifier: AGPL-3.0-only
"""Exact limits and deterministic restoration without external tokenizers/models."""

from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.conversations.bounds import BoundedProvider, recent_window, wire_size
from app.conversations.models import Conversation
from tests.test_conversations import dialogue as dialogue_fixture

dialogue = dialogue_fixture


def test_message_and_attempt_limits(dialogue):
    store, owner, _ = dialogue
    store.policy = replace(store.policy, max_message_bytes=16, max_messages=2, max_attempts=2)
    cid = store.create(owner, "one")["conversation_id"]
    assert store.begin(owner, cid, "one", "hash", 0, "x" * 16) is None
    store.complete(owner, cid, "one", {"message": "y" * 16})
    with pytest.raises(HTTPException) as exc:
        store.begin(owner, cid, "two", "hash", 2, "hello")
    assert exc.value.status_code == 409
    second = store.create(owner, "two")["conversation_id"]
    with pytest.raises(HTTPException) as exc:
        store.begin(owner, second, "one", "hash", 0, "x" * 17)
    assert exc.value.status_code == 413
    with pytest.raises(HTTPException) as exc:
        store.create(owner, "three")
    assert exc.value.status_code == 409


def test_pages_include_wire_bytes_and_scoped_cursors(dialogue):
    store, owner, _ = dialogue
    store.policy = replace(store.policy, page_messages=1)
    cid = store.create(owner, "one")["conversation_id"]
    store.begin(owner, cid, "one", "hash", 0, "hello")
    store.complete(owner, cid, "one", {"message": "\x01" * 8192})
    page = store.history(owner, cid)
    assert len(page["messages"]) == 1
    assert wire_size(page) <= store.policy.page_bytes
    cursor = page["before"]
    assert store.history(owner, cid, cursor)["messages"][0]["text"] == "hello"
    other = store.create(owner, "other")["conversation_id"]
    with pytest.raises(HTTPException) as exc:
        store.history(owner, other, cursor)
    assert exc.value.status_code == 404
    with store.sessions() as session:
        row = session.get(Conversation, cid)
        assert row.byte_count > 8192 * 2  # JSON retry response is included, including escapes.


def test_storage_reservation_refuses_overflow_without_partial_write(dialogue):
    store, owner, _ = dialogue
    store.policy = replace(store.policy, max_message_bytes=16, max_stored_bytes=1152)
    cid = store.create(owner, "one")["conversation_id"]
    assert store.begin(owner, cid, "one", "hash", 0, "x" * 16) is None
    store.complete(owner, cid, "one", {"message": "y" * 16})
    with pytest.raises(HTTPException) as exc:
        store.begin(owner, cid, "two", "hash", 2, "x" * 16)
    assert exc.value.status_code == 409
    assert len(store.history(owner, cid)["messages"]) == 2


def test_context_keeps_recent_complete_pairs_and_reserves_response(dialogue):
    store, _, _ = dialogue
    history = [
        {"role": role, "text": str(i) * 40} for i in range(3) for role in ["student", "assistant"]
    ]
    newest = [
        {"who": "student", "text": "2" * 40},
        {"who": "echo", "text": "2" * 40},
        {"who": "student", "text": "new"},
    ]
    policy = replace(store.policy, context_tokens=wire_size(newest) + 100, response_tokens=100)
    assert recent_window(history, "new", "echo", policy) == newest
    assert history[0]["text"] == "0" * 40  # Context truncation never deletes saved history.
    minimum = wire_size([{"who": "student", "text": "new"}]) + 100
    assert (
        recent_window(history, "new", "echo", replace(policy, context_tokens=minimum))
        == newest[-1:]
    )
    with pytest.raises(HTTPException) as exc:
        recent_window([], "new", "echo", replace(policy, context_tokens=minimum - 1))
    assert exc.value.status_code == 413


def test_provider_checks_full_prompt_and_caps_generation(dialogue):
    store, _, _ = dialogue
    calls = []

    class Stub:
        name = "offline"

        def json(self, **kwargs):
            calls.append(kwargs)
            return {"ok": True}

    policy = replace(store.policy, model_tokens=400, response_tokens=100)
    provider = BoundedProvider(Stub(), policy)
    assert provider.json(
        role="planner", tier="fast", system="x" * 20, user="y" * 24, max_tokens=800
    ) == {"ok": True}
    assert calls[0]["max_tokens"] == 100
    with pytest.raises(HTTPException) as exc:
        provider.json(role="reasoner", tier="strong", system="x" * 20, user="y" * 25)
    assert exc.value.status_code == 413 and len(calls) == 1
