# SPDX-License-Identifier: AGPL-3.0-only
"""Child-process SDK scenario. Not a server or a real model entry."""

import ipaddress
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from app.controlled_runtime import check, load, runtime_host

directory = Path(sys.argv[1])
manifest = load(directory)
check(directory)

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.llm import get_provider
from app.config import settings
from app.controls.contracts import Limits
from app.controls.jobs_http import execution_store
from app.controls.jobs_worker import AskAdapter
from app.controls.ledger import attempts
from app.controls.worker import run_one
from app.core.registry import get_active_pack
from app.store import ConsentRouter, SqlStore
from conftest import _CallStub

# No outward SDK calls, even if the registry/adapter wiring regresses.
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex


def guarded_connect(sock, address):
    # Windows asyncio's socketpair uses loopback internally; permit that only.
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return original_connect(sock, address)
    raise AssertionError("external network forbidden in SDK scenario")


def guarded_connect_ex(sock, address):
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return original_connect_ex(sock, address)
    raise AssertionError("external network forbidden in SDK scenario")


patch.object(socket.socket, "connect", guarded_connect).start()
patch.object(socket.socket, "connect_ex", guarded_connect_ex).start()
calls: list[dict] = []
constructors: list[dict] = []
responses: list[dict] = []
fault: Exception | None = None


def create(**kwargs):
    global fault
    calls.append(kwargs)
    if fault:
        error = fault
        fault = None
        raise error
    text = json.dumps(responses.pop(0))
    if settings.provider == "openai_compatible":
        return NS(
            choices=[NS(message=NS(content=text))], usage=NS(prompt_tokens=10, completion_tokens=5)
        )
    return NS(
        content=[NS(type="text", text=text)],
        usage=NS(
            input_tokens=6,
            cache_creation_input_tokens=2,
            cache_read_input_tokens=2,
            output_tokens=5,
        ),
    )


class SDK:
    def __init__(self, **kwargs):
        constructors.append(kwargs)
        self.chat = NS(completions=NS(create=create))
        self.messages = NS(create=create)


import anthropic
import openai

patch.object(openai, "OpenAI", SDK).start()
patch.object(anthropic, "Anthropic", SDK).start()
from app.main import app

host = runtime_host(directory, manifest)
client = TestClient(app, headers={"Authorization": "Bearer " + host.token()})
store = execution_store()
adapter = AskAdapter(store, ConsentRouter(SqlStore()), get_active_pack(), get_provider)
checks = 0
clock = __import__("time").time()


def expect(value):
    global checks
    assert value
    checks += 1


def answer_queue(error=None):
    responses[:] = [
        _CallStub().json(role=role, tier="fast", system="", user="")
        for role in ("planner", "reasoner", "self_eval")
    ]

    if error:
        responses[1]["message"] = (
            "Local model stub: "
            + error
            + ". This run did not finish; inspect the reported student line."
        )


def inference_calls():
    if settings.provider != "local_stub":
        return len(calls)
    with store.ledger.transaction() as conn:
        return len(conn.execute(select(attempts.c.id).where(attempts.c.kind == "model")).all())


def get_status(prefix, request_id):
    global clock
    clock += 3
    store.ledger.clock = lambda: clock
    return client.get(prefix + "/by-request/" + request_id)


curriculum = client.get("/api/curriculum")
expect(curriculum.status_code == 200)
expect(len([e for m in curriculum.json()["modules"] for e in m["exercises"]]) == 3)
run = client.post(
    "/api/run",
    json={"participant_id": "gh:12345", "exercise_id": "ds-foundations", "source": "print(7)"},
)
expect(run.status_code == 200 and run.json()["ok"] is True)
expect("7" in run.json()["pack"]["stdout"])

failed_run = client.post(
    "/api/run",
    json={
        "participant_id": "gh:12345",
        "exercise_id": "ds-foundations",
        "source": "raise ValueError('wrong exercise')",
    },
)
expect(failed_run.status_code == 200 and not failed_run.json()["ok"])
expect(failed_run.json()["pack"]["execution_status"] == "student_error")
expect(client.get("/api/curriculum").status_code == 200)

body = {
    "participant_id": "gh:12345",
    "exercise_id": "ds-foundations",
    "exercise_version": "local-v1",
    "event": "run",
    "stance": "peer",
    "source": "print(7)",
    "result": run.json(),
    "recent": [],
}

for saved in (False, True):
    prefix = "/api/sol/jobs"
    payload = {
        **body,
        "result": failed_run.json(),
        "source": "raise ValueError('wrong exercise')",
        "request_id": "saved_request_0001" if saved else "unsaved_request_0001",
    }
    if saved:
        conversation = client.post(
            "/api/conversations",
            json={
                "exercise_id": "ds-foundations",
                "exercise_version": "local-v1",
                "save": True,
                "request_id": "create_request_0001",
            },
        )
        expect(conversation.status_code < 300)
        cid = conversation.json()["conversation_id"]
        prefix = f"/api/conversations/{cid}/jobs"
        payload.pop("recent")
        payload.pop("event")
        payload.update(message="Explain the run", expected_revision=0)
    answer_queue("ValueError on student line 1 means an unsuitable value")
    before = inference_calls()
    first = client.post(prefix, json=payload)
    assert first.status_code == 202, (saved, first.text)
    expect(first.status_code == 202)
    duplicate = client.post(prefix, json=payload)
    expect(duplicate.status_code == 202 and duplicate.json()["id"] == first.json()["id"])
    expect(run_one(store.admission, adapter) and not run_one(store.admission, adapter))
    expect(inference_calls() - before == 3)
    result = get_status(prefix, payload["request_id"])
    expect(result.status_code == 200 and result.json()["state"] == "completed")
    expect("ValueError" in result.json()["result"]["message"])
    expect(get_status(prefix, payload["request_id"]).json()["result"] == result.json()["result"])
    if saved:
        history = client.get(f"/api/conversations/{cid}/messages").json()
        expect(len(history["messages"]) == 2 and history["revision"] == 2)
    expect(client.post(prefix, json=payload).json()["id"] == first.json()["id"])
    expect(inference_calls() - before == 3)

# Success, syntax error and failed checks, each with saving on and off.
from app.packs.datascience.solutions import SOLUTIONS

for case, source in (
    ("success", SOLUTIONS["ds-foundations"]["source"]),
    ("syntax", ".."),
    ("checks", "result = {}"),
):
    executed = client.post(
        "/api/run",
        json={"participant_id": "gh:12345", "exercise_id": "ds-foundations", "source": source},
    )
    expect(executed.status_code == 200)
    expect(executed.json()["ok"] == (case != "syntax"))
    expect(client.get("/api/curriculum").status_code == 200)
    for saved in (False, True):
        prefix = "/api/sol/jobs"
        payload = {
            **body,
            "source": source,
            "result": executed.json(),
            "request_id": f"{case}_{saved}_request_0001",
        }
        if saved:
            conversation = client.post(
                "/api/conversations",
                json={
                    "exercise_id": "ds-foundations",
                    "exercise_version": "local-v1",
                    "save": True,
                    "request_id": f"create_{case}_request_0001",
                },
            )
            expect(conversation.status_code < 300)
            cid = conversation.json()["conversation_id"]
            prefix = f"/api/conversations/{cid}/jobs"
            payload.pop("recent")
            payload.pop("event")
            payload.update(message="Explain this run", expected_revision=0)
        answer_queue(
            "SyntaxError on student line 1 means Python cannot parse punctuation"
            if case == "syntax"
            else None
        )
        before = inference_calls()
        first = client.post(prefix, json=payload)
        assert first.status_code == 202, first.text
        expect(client.post(prefix, json=payload).json()["id"] == first.json()["id"])
        expect(run_one(store.admission, adapter) and not run_one(store.admission, adapter))
        result = get_status(prefix, payload["request_id"])
        expect(result.status_code == 200 and result.json()["state"] == "completed")
        expect(bool(result.json()["result"]["message"].strip()))
        expect(inference_calls() - before == 3)
        if case == "syntax":
            expect("SyntaxError" in result.json()["result"]["message"])
            expect(executed.json()["pack"]["error_line"] == 1)
            if calls:
                expect("SyntaxError" in json.dumps(calls[before:]))
        if saved:
            history = client.get(f"/api/conversations/{cid}/messages").json()
            expect(len(history["messages"]) == 2 and history["revision"] == 2)

# Queued original principal revoked while another still has identical scope.
path = directory / "authorization.json"
auth = json.loads(path.read_text())
auth["subjects"]["other"] = auth["subjects"]["local-demo-learner"]
path.write_text(json.dumps(auth))
revoked = {**body, "request_id": "revoked_request_0001", "event": "chat"}
queued = client.post("/api/sol/jobs", json=revoked)
expect(queued.status_code == 202)
del auth["subjects"]["local-demo-learner"]
path.write_text(json.dumps(auth))
before = inference_calls()
expect(run_one(store.admission, adapter) and inference_calls() == before)
expect(client.get("/api/sol/jobs/" + queued.json()["id"]).status_code in (401, 404))
auth["subjects"]["local-demo-learner"] = auth["subjects"]["other"]
path.write_text(json.dumps(auth))

if settings.provider == "local_stub":
    expect(store.ledger.summary()["consumed"]["microunits"] == 480)
    expect(not constructors and not calls)
    print(json.dumps({"provider": settings.provider, "checks": checks, "real_network_calls": 0}))
    raise SystemExit(0)

# Ambiguous external timeout keeps its allowance; no automatic retry/re-execution.
fault = TimeoutError("private SDK diagnostic")
timeout_body = {**body, "event": "chat", "request_id": "timeout_request_0001"}
expect(client.post("/api/sol/jobs", json=timeout_body).status_code == 202)
before = len(calls)
expect(run_one(store.admission, adapter))
expect(len(calls) == before + 1 and not run_one(store.admission, adapter))
expect(get_status("/api/sol/jobs", timeout_body["request_id"]).json()["state"] == "unknown")
summary = store.ledger.summary()
expect(summary["reserved"]["tokens"] > 0)
expect(summary["consumed"]["microunits"] == 480)  # 24 calls × (10*1+5*2)
expect(all(c["max_retries"] == 0 and c["timeout"] == 12 for c in constructors))
with store.ledger.transaction() as conn:
    model_rows = conn.execute(select(attempts).where(attempts.c.kind == "model")).mappings().all()
expect(len(model_rows) == 25 and sum(r["state"] == "unknown" for r in model_rows) == 1)

# Budget depletion is rejected before another SDK send, even after a timeout.
with store.ledger.transaction() as conn:
    policy = store.ledger.policy(conn)
store.ledger.update_policy(
    policy.model_copy(
        update={
            "version": "exhausted-test",
            "deployment": Limits(tokens=0, microunits=0, runs=0, wall_ms=0),
        }
    )
)
before = len(calls)
denied = client.post("/api/sol/jobs", json={**body, "request_id": "denied_request_00001"})
if denied.status_code == 202:
    run_one(store.admission, adapter)
expect(len(calls) == before)
print(json.dumps({"provider": settings.provider, "checks": checks, "real_network_calls": 0}))
