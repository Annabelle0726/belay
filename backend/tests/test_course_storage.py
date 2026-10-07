# SPDX-License-Identifier: AGPL-3.0-only
from app.auth import Identity
from app.store import ConsentRouter, InMemoryStore, make_event
from app.store.scoped import register, scoped_store


def test_course_state_survives_router_restart_without_research_consent():
    durable = InMemoryStore()
    identity = Identity("inst", "class", "gh:1", (("echo-1", "v1"),), "echo-1", "v1")
    router = ConsentRouter(durable)
    register(router, identity, False)
    scoped_store(router, identity).save_learner_state("gh:1", {"goals": {"text": "learn"}})
    scoped_store(router, identity).append_event(make_event("gh:1", "echo-1", "study", "run", {}))
    restarted = ConsentRouter(durable)
    assert scoped_store(restarted, identity).get_learner_state("gh:1")["goals"]["text"] == "learn"
    assert scoped_store(restarted, identity).attempts("gh:1", "echo-1") == 1
    assert durable.export_jsonl(identity.storage_id) == ""
    assert restarted._lookup_consent(identity.storage_id) is False


def test_course_initialization_never_changes_existing_research_consent():
    router = ConsentRouter(InMemoryStore())
    identity = Identity("inst", "class", "gh:1", ())
    register(router, identity, True)
    scoped_store(router, identity)
    assert router._lookup_consent(identity.storage_id) is True


def test_sql_course_state_and_counts_survive_restart_without_research(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.store import SqlStore, db
    from app.store.models import Base

    engine = create_engine("sqlite:///" + str(tmp_path / "course.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    identity = Identity("inst", "class", "gh:1", (("echo-1", "v1"),), "echo-1", "v1")
    try:
        router = ConsentRouter(SqlStore())
        scoped_store(router, identity).save_learner_state("gh:1", {"goals": {"text": "learn"}})
        scoped_store(router, identity).append_event(
            make_event("gh:1", "echo-1", "study", "run", {})
        )
        restarted = ConsentRouter(SqlStore())
        assert scoped_store(restarted, identity).attempts("gh:1", "echo-1") == 1
        assert (
            scoped_store(restarted, identity).get_learner_state("gh:1")["goals"]["text"] == "learn"
        )
        assert restarted.durable.export_jsonl(identity.storage_id) == ""
        assert restarted._lookup_consent(identity.storage_id) is False
    finally:
        engine.dispose()
