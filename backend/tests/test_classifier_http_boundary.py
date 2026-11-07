# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise the dedicated classifier's real SDK transport against loopback peers."""

import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.agent import injection_guard, run_turn
from app.config import settings
from app.controls.runtime import operation
from app.store import InMemoryStore
from conftest import CONTROL_SCOPE, _CallStub, _payload
from tests.test_controls_execution import funded

LEARNER = "PRIVATE_CLASSIFIER_LEARNER_SENTINEL"
SAFE = '{"flagged":false,"confidence":0.25}'


@contextmanager
def endpoint(*responses):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            status, headers, payload = responses[len(requests) - 1]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join()


def completion(content, reasoning=None):
    return (
        200,
        {},
        {
            "choices": [{"message": {"content": content, "reasoning_content": reasoning}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


@pytest.fixture
def guard(monkeypatch, caplog):
    caplog.set_level("INFO")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(settings, "injection_guard_enabled", True)
    monkeypatch.setattr(settings, "injection_guard_model", "synthetic-classifier")
    guard = injection_guard.InjectionGuard()
    monkeypatch.setattr(injection_guard, "_guard_instance", guard)
    yield guard
    if guard._llm is not None:
        guard._llm._client.close()


@pytest.mark.parametrize("status", [307, 308])
def test_classifier_never_follows_redirect_to_another_origin(
    monkeypatch, guard, ledger, status, caplog
):
    funded(ledger)
    with endpoint(completion(SAFE)) as (other, forwarded):
        redirect = status, {"Location": other + "/collect"}, {"error": "PRIVATE_DOWNSTREAM"}
        with endpoint(redirect) as (configured, sent):
            monkeypatch.setattr(settings, "injection_guard_endpoint", configured)
            with operation(ledger, CONTROL_SCOPE, "classifier"):
                verdict = guard.check(LEARNER)

    assert len(sent) == 1 and LEARNER in sent[0]["messages"][1]["content"]
    assert forwarded == []
    assert verdict.status == "error" and verdict.error_category == "LLM_INFERENCE_ERROR"
    for private in (LEARNER, "PRIVATE_DOWNSTREAM"):
        assert private not in str(verdict) and private not in caplog.text
    summary = ledger.summary()
    assert summary["attempts"] == 1 and summary["states"]["unknown"] == 1


@pytest.mark.parametrize(
    "content,reasoning",
    [
        ("PRIVATE_RESPONSE " + SAFE, None),
        (SAFE + " PRIVATE_RESPONSE", None),
        ("```json\n" + SAFE + "\n```", None),
        ("[" + SAFE + "]", None),
        (SAFE + SAFE, None),
        (None, SAFE),
        ("", SAFE),
        ('{"flagged":true,"flagged":false,"confidence":0.25}', None),
        ('{"flagged":false,"confidence":0.25,"extra":NaN}', None),
    ],
)
def test_only_complete_final_verdict_is_classifier_evidence(
    monkeypatch, guard, caplog, content, reasoning
):
    store = InMemoryStore()
    with endpoint(completion(content, reasoning)) as (configured, sent):
        monkeypatch.setattr(settings, "injection_guard_endpoint", configured)
        out = run_turn(_payload("p_strict", LEARNER, stance="control"), _CallStub(), store)

    assert len(sent) == 1
    evidence = out["components"]["injection"]
    assert evidence["status"] == "malformed" and evidence["error_category"] == "MALFORMED_JSON"
    trace = store.export_jsonl("p_strict")
    assert json.loads(trace)["payload"]["telemetry"]["injection"] == evidence
    for private in (LEARNER, "PRIVATE_RESPONSE"):
        assert private not in trace and private not in caplog.text


@pytest.mark.parametrize("status", [400, 422])
def test_explicit_format_fallback_gets_separate_attempt_on_configured_origin(
    monkeypatch, guard, ledger, status
):
    funded(ledger)
    with endpoint((status, {}, {"error": "unsupported format"}), completion(" \n" + SAFE)) as (
        configured,
        sent,
    ):
        monkeypatch.setattr(settings, "injection_guard_endpoint", configured)
        with operation(ledger, CONTROL_SCOPE, "classifier"):
            verdict = guard.check(LEARNER)

    assert verdict.status == "safe" and verdict.score == 0.25
    assert len(sent) == 2
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in sent[1]
    summary = ledger.summary()
    assert summary["attempts"] == 2
    assert summary["states"]["unknown"] == 1 and summary["states"]["settled"] == 1
