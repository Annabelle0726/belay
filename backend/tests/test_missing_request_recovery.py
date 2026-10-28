# SPDX-License-Identifier: AGPL-3.0-only
# Imported pytest fixtures use name-based injection.
# ruff: noqa: F811
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import select

from app.controls.admission import jobs
from app.controls.data import bindings, data
from app.controls.ledger import attempts
from tests.http_auth import token
from tests.test_execution_grants import grant_boundary  # noqa: F401
from tests.test_jobs_http import BODY, job_boundary  # noqa: F401

ROUTE = "/api/sol/jobs"
RECOVER = ROUTE + "/by-request/" + BODY["request_id"] + "/reconcile"
CONTEXT = {"request_id": BODY["request_id"], "exercise_id": "echo-1", "exercise_version": "v1"}


def test_absent_recovery_fences_late_submission_without_spending(job_boundary):
    client, store, _, _ = job_boundary
    assert client.get(ROUTE + "/config").json()["missing_request_recovery"] == 1
    response = client.post(RECOVER, json=CONTEXT)
    assert response.status_code == 200
    assert response.json()["reason"] == "request_not_admitted"
    assert client.post(RECOVER, json=CONTEXT).json() == response.json()
    assert client.post(ROUTE, json=BODY).status_code == 409
    assert store.admission.claim() is None
    with store.ledger.transaction() as conn:
        assert not list(conn.execute(select(attempts)))
        assert not list(conn.execute(select(data)))
        assert len(list(conn.execute(select(jobs)))) == 1


def test_existing_or_foreign_request_is_never_retired(job_boundary):
    client, store, _, _ = job_boundary
    job = client.post(ROUTE, json=BODY).json()
    foreign = client.post(
        RECOVER, json=CONTEXT, headers={"Authorization": "Bearer " + token("other")}
    )
    assert foreign.status_code == 404
    response = client.post(RECOVER, json=CONTEXT)
    assert response.status_code == 200 and response.json()["state"] == "queued"
    with store.ledger.transaction() as conn:
        conn.execute(
            jobs.update().where(jobs.c.id == job["id"]).values(state="unknown", last_poll=None)
        )
    assert client.post(RECOVER, json=CONTEXT).json()["state"] == "unknown"
    with store.ledger.transaction() as conn:
        assert len(list(conn.execute(select(attempts)))) == 1


def test_orphan_evidence_or_revocation_cannot_be_closed(job_boundary):
    client, store, path, auth = job_boundary
    job = client.post(ROUTE, json=BODY).json()
    with store.ledger.transaction() as conn:
        conn.execute(jobs.delete().where(jobs.c.id == job["id"]))
        conn.execute(bindings.delete().where(bindings.c.id == job["id"]))
    response = client.post(RECOVER, json=CONTEXT)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "execution_unknown"
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    assert client.post(RECOVER, json=CONTEXT).status_code == 404


def test_admission_racing_recovery_has_one_serialized_outcome(job_boundary):
    client, store, _, _ = job_boundary
    gate = Barrier(2)

    def action(path, body):
        gate.wait()
        return client.post(path, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        submit = pool.submit(action, ROUTE, BODY)
        recover = pool.submit(action, RECOVER, CONTEXT)
        sent, checked = submit.result(), recover.result()
    assert checked.status_code == 200
    if sent.status_code == 202:
        assert checked.json()["state"] == "queued"
    else:
        assert sent.status_code == 409
        assert checked.json()["reason"] == "request_not_admitted"
    with store.ledger.transaction() as conn:
        assert len(list(conn.execute(select(jobs)))) == 1
        assert len(list(conn.execute(select(attempts)))) == (sent.status_code == 202)


def test_operator_continuation_is_owned_policy_bound_and_keeps_unknown(job_boundary, monkeypatch):
    from app.config import settings

    client, store, _, _ = job_boundary
    job = client.post(ROUTE, json=BODY).json()
    with store.ledger.transaction() as conn:
        policy = store.ledger.policy(conn)
        conn.execute(jobs.update().where(jobs.c.id == job["id"]).values(state="unknown"))
        before = list(conn.execute(select(attempts)).mappings())
    assert client.get(ROUTE + "/config").json()["operator_continuations"] == []
    approval = {"policy_version": policy.version, "request_ids": [BODY["request_id"]]}
    monkeypatch.setattr(settings, "controls_operator_continuations", json.dumps(approval))
    assert client.get(ROUTE + "/config").json()["operator_continuations"] == [BODY["request_id"]]
    assert (
        client.get(ROUTE + "/config", headers={"Authorization": "Bearer " + token("other")}).json()[
            "operator_continuations"
        ]
        == []
    )
    monkeypatch.setattr(
        settings,
        "controls_operator_continuations",
        json.dumps({**approval, "policy_version": "stale"}),
    )
    assert client.get(ROUTE + "/config").json()["operator_continuations"] == []
    monkeypatch.setattr(settings, "controls_operator_continuations", "malformed")
    assert client.get(ROUTE + "/config").json()["operator_continuations"] == []
    with store.ledger.transaction() as conn:
        assert (
            conn.execute(select(jobs.c.state).where(jobs.c.id == job["id"])).scalar_one()
            == "unknown"
        )
        assert list(conn.execute(select(attempts)).mappings()) == before
