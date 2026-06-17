# SPDX-License-Identifier: AGPL-3.0-only
"""
SqlStore integration tests against the configured DATABASE_URL.

Run against Postgres:
    export DATABASE_URL=postgresql+psycopg://qi:qi@localhost:5432/qimvp
    pytest tests/test_sql_store.py

Run against SQLite (default, no export needed):
    pytest tests/test_sql_store.py

IMPORTANT: every test that writes a learner_state or event MUST create the
Participant row first.  SQLite ignores FK constraints; Postgres enforces them.
All helpers below call _mk_participant() before any dependent write.
"""

from __future__ import annotations

import json
import uuid

from app.store import SqlStore, make_event
from app.store.db import DATABASE_URL, SessionLocal, engine, init_db
from app.store.models import LearnerState, Participant

# ── shared helpers ────────────────────────────────────────────────────────────


def _pid() -> str:
    """Unique participant id per call — avoids cross-test collisions."""
    return "t_" + uuid.uuid4().hex[:12]


def _mk_participant(pid: str, consent: bool = True) -> None:
    """Insert a Participant row directly so FK constraints pass on Postgres."""
    with SessionLocal() as s:
        s.add(Participant(id=pid, anon_code="code_" + pid[-6:], consent=consent))
        s.commit()


def _mk_store() -> SqlStore:
    return SqlStore()


# ── 1. init_db is idempotent ──────────────────────────────────────────────────


class TestInitDb:
    def test_init_db_idempotent_and_creates_tables(self):
        init_db()
        init_db()  # second call must not raise
        from sqlalchemy import inspect as sa_inspect

        tables = set(sa_inspect(engine).get_table_names())
        assert {"participants", "learner_state", "events"}.issubset(
            tables
        ), f"expected all three tables, got {sorted(tables)}"


# ── 2. engine dialect matches DATABASE_URL ────────────────────────────────────


class TestEngineDialect:
    def test_dialect_matches_database_url(self):
        dialect = engine.dialect.name
        if DATABASE_URL.startswith("postgresql"):
            assert dialect == "postgresql", f"expected postgresql, got {dialect}"
        else:
            assert dialect == "sqlite", f"expected sqlite, got {dialect}"


# ── 3. unknown pid returns empty defaults ─────────────────────────────────────


class TestGetLearnerStateUnknown:
    def test_unknown_pid_returns_defaults(self):
        state = _mk_store().get_learner_state("no_such_pid_" + uuid.uuid4().hex)
        assert state == {
            "grasped": [],
            "shaky": [],
            "attempts": 0,
            "concepts": {},
            "goals": None,
            "reflections": [],
            "overlay": None,
        }


# ── 4. save + get round-trips all fields including concepts ───────────────────


class TestLearnerStateRoundTrip:
    def test_save_then_get_roundtrip(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        store.save_learner_state(
            pid, {"grasped": ["entanglement"], "shaky": ["phase"], "attempts": 5}
        )
        got = store.get_learner_state(pid)
        assert got["grasped"] == ["entanglement"]
        assert got["shaky"] == ["phase"]
        assert got["attempts"] == 5

    def test_concepts_column_round_trips(self):
        """LearnerState.concepts JSON column persists and restores structured mastery."""
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        snapshot = {
            "entanglement": {
                "state": "shaky",
                "evidence": 2,
                "last_seen": "2026-06-03T00:00:00+00:00",
                "last_review": None,
                "last_review_ex": None,
            },
            "superposition": {
                "state": "grasped",
                "evidence": 3,
                "last_seen": "2026-06-03T00:00:00+00:00",
                "last_review": "2026-06-03T00:01:00+00:00",
                "last_review_ex": "bell",
            },
        }
        store.save_learner_state(
            pid, {"grasped": [], "shaky": [], "attempts": 0, "concepts": snapshot}
        )
        got = store.get_learner_state(pid)
        assert got["concepts"]["entanglement"]["state"] == "shaky"
        assert got["concepts"]["superposition"]["state"] == "grasped"
        assert got["concepts"]["superposition"]["last_review_ex"] == "bell"


# ── 5. save twice upserts (no duplicate row) ─────────────────────────────────


class TestLearnerStateUpsert:
    def test_save_twice_overwrites_no_duplicate(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        store.save_learner_state(pid, {"grasped": ["a"], "shaky": [], "attempts": 1})
        store.save_learner_state(pid, {"grasped": ["a", "b"], "shaky": ["c"], "attempts": 2})
        got = store.get_learner_state(pid)
        assert got["grasped"] == ["a", "b"]
        assert got["shaky"] == ["c"]
        assert got["attempts"] == 2
        # Exactly one row in learner_state
        with SessionLocal() as s:
            count = s.query(LearnerState).filter_by(participant_id=pid).count()
        assert count == 1


# ── 6. append one run event → export returns it ───────────────────────────────


class TestAppendAndExport:
    def test_append_run_event_appears_in_export(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        store.append_event(
            make_event(pid, "bell", "study", "run", {"source": "allocate 2"}, stance="peer")
        )
        jsonl = store.export_jsonl(pid)
        rows = [json.loads(l) for l in jsonl.strip().split("\n") if l.strip()]
        assert len(rows) == 1
        assert rows[0]["participant_id"] == pid
        assert rows[0]["event_type"] == "run"


# ── 7. N events → N rows (append-only) ───────────────────────────────────────


class TestAppendOnly:
    def test_n_appends_produce_n_rows(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        for _ in range(4):
            store.append_event(
                make_event(pid, "bell", "study", "run", {"source": "x"}, stance="peer")
            )
        rows = [l for l in store.export_jsonl(pid).strip().split("\n") if l.strip()]
        assert len(rows) == 4


# ── 8. attempts() counts only event_type == "run" ────────────────────────────


class TestAttemptsCountsOnlyRun:
    def test_turn_event_does_not_increment_attempts(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        store.append_event(make_event(pid, "bell", "study", "run", {}, stance="peer"))
        store.append_event(make_event(pid, "bell", "study", "turn", {}, stance="peer"))
        store.append_event(make_event(pid, "bell", "study", "run", {}, stance="peer"))
        assert store.attempts(pid, "bell") == 2


# ── 9. attempts() scoped by participant_id AND exercise_id ────────────────────


class TestAttemptsIsolation:
    def test_attempts_isolated_by_pid_and_exercise(self):
        p1, p2 = _pid(), _pid()
        _mk_participant(p1)
        _mk_participant(p2)
        store = _mk_store()
        store.append_event(make_event(p1, "bell", "study", "run", {}, stance="peer"))
        store.append_event(make_event(p1, "superpose", "study", "run", {}, stance="peer"))
        store.append_event(make_event(p2, "bell", "study", "run", {}, stance="peer"))
        assert store.attempts(p1, "bell") == 1
        assert store.attempts(p1, "superpose") == 1
        assert store.attempts(p2, "bell") == 1


# ── 10. export_jsonl(None) returns all rows, ordered by ts ────────────────────


class TestExportAll:
    def test_export_all_ordered_by_ts(self):
        p1, p2 = _pid(), _pid()
        _mk_participant(p1)
        _mk_participant(p2)
        store = _mk_store()
        store.append_event(make_event(p1, "bell", "study", "run", {}, stance="peer"))
        store.append_event(make_event(p2, "bell", "study", "run", {}, stance="peer"))
        all_rows = [
            json.loads(l) for l in store.export_jsonl(None).strip().split("\n") if l.strip()
        ]
        our_pids = {p1, p2}
        our_rows = [r for r in all_rows if r["participant_id"] in our_pids]
        assert len(our_rows) >= 2
        ts_vals = [r["ts"] for r in our_rows]
        assert ts_vals == sorted(ts_vals), "rows should be ordered by ts"


# ── 11. export_jsonl(pid) returns only that pid's rows ────────────────────────


class TestExportFiltered:
    def test_export_filtered_by_pid(self):
        p1, p2 = _pid(), _pid()
        _mk_participant(p1)
        _mk_participant(p2)
        store = _mk_store()
        store.append_event(make_event(p1, "bell", "study", "run", {}, stance="peer"))
        store.append_event(make_event(p2, "bell", "study", "run", {}, stance="peer"))
        rows_p1 = [json.loads(l) for l in store.export_jsonl(p1).strip().split("\n") if l.strip()]
        assert all(r["participant_id"] == p1 for r in rows_p1)
        assert len(rows_p1) == 1


# ── 12. nested payload round-trips through JSON column ───────────────────────


class TestNestedPayloadRoundTrip:
    def test_nested_payload_byte_equivalent(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        payload = {
            "event": "turn",
            "stance": "peer",
            "telemetry": {
                "escalated": False,
                "abstained": False,
                "reasoning_effort": "high",
                "confidence_trajectory": {"planner": 0.65, "reasoner": 0.82, "self_eval": 0.71},
                "misconception_id": "M2.1-superpose-both-is-entangle",
            },
        }
        store.append_event(make_event(pid, "bell", "study", "turn", payload, stance="peer"))
        rows = [json.loads(l) for l in store.export_jsonl(pid).strip().split("\n") if l.strip()]
        assert len(rows) == 1
        got = rows[0]["payload"]
        assert got["telemetry"]["misconception_id"] == "M2.1-superpose-both-is-entangle"
        assert got["telemetry"]["confidence_trajectory"] == {
            "planner": 0.65,
            "reasoner": 0.82,
            "self_eval": 0.71,
        }
        assert got["telemetry"]["escalated"] is False
        assert got["telemetry"]["reasoning_effort"] == "high"


# ── 13. stance=None persists and re-exports as null ───────────────────────────


class TestStanceNull:
    def test_stance_none_roundtrips_as_null(self):
        pid = _pid()
        _mk_participant(pid)
        store = _mk_store()
        store.append_event(make_event(pid, "bell", "study", "run", {}, stance=None))
        rows = [json.loads(l) for l in store.export_jsonl(pid).strip().split("\n") if l.strip()]
        assert len(rows) == 1
        assert rows[0]["stance"] is None


# ── 14. durability: write with one SqlStore, read with a fresh one ─────────────


class TestDurability:
    def test_fresh_store_reads_persisted_rows(self):
        pid = _pid()
        _mk_participant(pid)
        store1 = _mk_store()
        store1.save_learner_state(pid, {"grasped": ["ghz"], "shaky": [], "attempts": 7})
        store1.append_event(
            make_event(pid, "ghz", "study", "run", {"source": "allocate 3"}, stance="oracle")
        )

        # Fresh SqlStore — cold start, no in-process state
        store2 = _mk_store()
        state = store2.get_learner_state(pid)
        assert state["grasped"] == ["ghz"]
        assert state["attempts"] == 7

        rows = [json.loads(l) for l in store2.export_jsonl(pid).strip().split("\n") if l.strip()]
        assert len(rows) == 1
        assert rows[0]["stance"] == "oracle"
