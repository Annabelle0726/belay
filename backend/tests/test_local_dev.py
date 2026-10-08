# SPDX-License-Identifier: AGPL-3.0-only
"""Loopback host and real backend checks without any identity/model service."""

import http.client
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import jwt
import pytest

from app.local_dev import AUDIENCE, LEARNER, SUBJECT, DemoHost, lock_directory

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def host():
    demo = DemoHost("http://127.0.0.1:8000")
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), demo.handler(BACKEND.parent / "frontend"))
    demo.origin = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield demo, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_host_issues_verified_short_lived_tokens_without_cors_or_persistence(host, capsys):
    demo, _ = host
    with urlopen(demo.origin + "/__belay_local__/token", timeout=5) as response:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "Access-Control-Allow-Origin" not in response.headers
        token = json.load(response)["access_token"]
    claims = jwt.decode(
        token, demo.key.public_key(), algorithms=["RS256"], issuer=demo.origin, audience=AUDIENCE
    )
    assert claims["sub"] == SUBJECT and claims["exp"] - claims["iat"] == 300
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.invalid"},
        {"Origin": "https://attacker.invalid"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "null"},
    ],
)
def test_foreign_browser_requests_cannot_get_tokens_or_bootstrap(host, headers):
    demo, server = host
    for path in ["/__belay_local__/token", "/__belay_local__/bootstrap.js", "/dev-client.html"]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        assert response.status == 403
        assert "access_token" not in response.read().decode()
        connection.close()


def test_all_demos_load_bootstrap_before_auth_and_only_public_configuration(host):
    demo, _ = host
    for page in ["dev-client.html", "widget.html", "embed-demo.html"]:
        with urlopen(demo.origin + "/" + page, timeout=5) as response:
            html = response.read().decode()
        assert html.index("/__belay_local__/bootstrap.js") < html.index('src="auth-client.js"')
        assert 'value="http://127.0.0.1:8000"' in html
        assert "access_token" not in html and "PRIVATE KEY" not in html
    with urlopen(demo.origin + "/__belay_local__/bootstrap.js", timeout=5) as response:
        js = response.read().decode()
    assert "BELAY_GET_ACCESS_TOKEN" in js and LEARNER in js
    assert "localStorage" not in js and "sessionStorage" not in js
    assert "cache: 'no-store'" in js and "credentials: 'omit'" in js


@pytest.mark.parametrize("port_option", ["--api-port", "--frontend-port"])
@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0", "::"])
def test_busy_port_fails_before_creating_data(tmp_path, port_option, address):
    family = socket.AF_INET6 if address == "::" else socket.AF_INET
    if family == socket.AF_INET6 and not socket.has_ipv6:
        pytest.skip("IPv6 unavailable")
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        if family == socket.AF_INET6:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        try:
            listener.bind((address, 0))
        except OSError:
            if family == socket.AF_INET6:
                pytest.skip("IPv6 loopback unavailable")
            raise
        listener.listen()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.local_dev",
                port_option,
                str(listener.getsockname()[1]),
                "--frontend-port" if port_option == "--api-port" else "--api-port",
                "0",
                "--data-dir",
                str(tmp_path / "unused"),
            ],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    assert result.returncode == 2 and "stop existing servers" in result.stderr
    assert not (tmp_path / "unused").exists()


def test_directory_lock_blocks_concurrent_launchers_and_releases_on_close(tmp_path):
    with lock_directory(tmp_path):
        with pytest.raises(OSError):
            lock_directory(tmp_path)
    with lock_directory(tmp_path):
        pass


@pytest.mark.parametrize("ledger", [None, "broken\n"])
def test_existing_database_never_gets_a_replacement_deletion_ledger(tmp_path, ledger):
    (tmp_path / "demo.sqlite3").touch()
    if ledger is not None:
        (tmp_path / "deletions.jsonl").write_text(ledger)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.local_dev",
            "--api-port",
            "0",
            "--frontend-port",
            "0",
            "--data-dir",
            str(tmp_path),
            "--env-file",
            str(tmp_path / "no.env"),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={**os.environ, "TUTOR_PACK": "_skeleton"},
    )
    assert result.returncode == 2 and "local deletion ledger" in result.stderr
    assert "Traceback" not in result.stderr
    if ledger is None:
        assert not (tmp_path / "deletions.jsonl").exists()
    else:
        assert (tmp_path / "deletions.jsonl").read_text() == ledger


def test_restart_rotates_signing_key_and_preserves_attempt_and_deletion_fences(tmp_path):
    script = """
import json, sys
from pathlib import Path
from app.local_dev import DemoHost, configure
host = DemoHost('http://127.0.0.1:8000')
host.origin = 'http://127.0.0.1:5173'
configure(host, Path(sys.argv[1]), True)
from app.auth import Identity
from app.config import settings
from app.conversations.policy import Policy
from app.conversations.repository import ConversationStore
from app.store.db import engine
owner = Identity('local-demo', 'local-class', 'gh:12345', (('echo-1', 'local-v1'),),
                 'echo-1', 'local-v1', (('echo-1', 'local-v1'),))
repo = ConversationStore(engine, Policy.from_settings(settings))
print(json.dumps(repo.create(owner, 'restart-create')))
engine.dispose()
"""

    def provision():
        result = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)],
            cwd=BACKEND,
            env={**os.environ, "TUTOR_PACK": "_skeleton"},
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    first = provision()
    key = (tmp_path / "public-key.pem").read_bytes()
    ledger = tmp_path / "deletions.jsonl"
    fences = ledger.read_text() + '{"conversation_id":"' + "a" * 32 + '"}\n'
    ledger.write_text(fences)
    second = provision()
    assert first["conversation_id"] == second["conversation_id"]
    assert (tmp_path / "public-key.pem").read_bytes() != key
    assert ledger.read_text() == fences


@pytest.mark.parametrize("saving", [False, True])
def test_launcher_real_auth_course_and_optional_dialogue(tmp_path, saving):
    env = dict(os.environ)
    env.update(
        TUTOR_PACK="_skeleton",
        PROVIDER="openai_compatible",
        OPENAI_API_KEY="EMPTY",
        OPENAI_BASE_URL="http://model.invalid.test/v1",
    )
    # Windows asyncio uses an internal loopback socket pair. Permit that, but
    # forbid DNS/network to external identity or model services in the child.
    wrapper = (
        "import socket\n"
        "original = socket.getaddrinfo\n"
        "def local_only(address, *args, **kwargs):\n"
        "    if address not in ('127.0.0.1', 'localhost', '::1', None):\n"
        "        raise AssertionError('outbound forbidden')\n"
        "    return original(address, *args, **kwargs)\n"
        "socket.getaddrinfo = local_only\n"
        "from app.local_dev import main\nmain()"
    )
    args = [
        sys.executable,
        "-u",
        "-c",
        wrapper,
        "--api-port",
        "0",
        "--frontend-port",
        "0",
        "--env-file",
        str(tmp_path / "no.env"),
        "--data-dir",
        str(tmp_path),
    ]
    if saving:
        args.append("--save-dialogue")
    process = subprocess.Popen(
        args, cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    output = queue.Queue()

    def read_lines():
        for line in process.stdout:
            output.put(line)

    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()
    try:
        frontend = (
            output.get(timeout=30)
            .strip()
            .removeprefix("Local demo: ")
            .removesuffix("/dev-client.html")
        )
        backend = output.get(timeout=30).split(";")[0].removeprefix("Backend: ")
        assert frontend.startswith("http://127.0.0.1:") and backend.startswith("http://127.0.0.1:")

        def request(path, body=None, headers=None, origin=backend):
            data = json.dumps(body).encode() if body is not None else None
            req = Request(
                origin + path,
                data=data,
                headers={"Content-Type": "application/json", **(headers or {})},
            )
            try:
                response = urlopen(req, timeout=5)
            except URLError as error:
                if not hasattr(error, "code"):
                    raise
                response = error
            with response:
                return response.code, json.load(response)

        deadline = time.monotonic() + 20
        while True:
            try:
                assert request("/healthz")[0] == 200
                break
            except URLError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        assert request("/api/curriculum")[0] == 401
        status, credentials = request("/__belay_local__/token", origin=frontend)
        assert status == 200
        headers = {"Authorization": "Bearer " + credentials["access_token"]}
        assert request("/api/curriculum", headers=headers)[0] == 200
        status, config = request("/api/conversations/config", headers=headers)
        assert status == 200 and config["enabled"] is saving
        assert config["identity"]["learner_id"] == LEARNER
        assert (
            request("/api/participant", {"anon_code": "gh:2", "consent": False}, headers)[0] == 404
        )
        status, registered = request(
            "/api/participant", {"anon_code": LEARNER, "consent": False}, headers
        )
        assert status == 200 and registered["anon_code"] == LEARNER
        body = {
            "exercise_id": "echo-1",
            "exercise_version": "local-v1",
            "save": True,
            "request_id": "create-1",
        }
        status, attempt = request("/api/conversations", body, headers)
        if not saving:
            assert status == 409
            assert (tmp_path / "deletions.jsonl").read_text() == '{"schema":1}\n'
        else:
            assert status == 200, attempt
            cid = attempt["conversation_id"]
            turn = {
                "request_id": "turn-1",
                "expected_revision": 0,
                "message": "Explain loops",
                "stance": "control",
            }
            status, released = request("/api/conversations/" + cid + "/turns", turn, headers)
            assert status == 200, released
            status, history = request(
                "/quad/v1/conversations/" + cid + "/messages", headers=headers
            )
            assert status == 200 and len(history["messages"]) == 2
            assert history["messages"][0]["text"] == "Explain loops"
            assert (tmp_path / "deletions.jsonl").read_text() == '{"schema":1}\n'
        assert set(p.name for p in tmp_path.iterdir()) <= {
            "public-key.pem",
            "authorization.json",
            "demo.sqlite3",
            "deletions.jsonl",
            "launcher.lock",
        }
        assert "PRIVATE KEY" not in (tmp_path / "public-key.pem").read_text()
    finally:
        process.terminate()
        _, errors = process.communicate(timeout=15)
        reader.join(timeout=5)
    assert "outbound forbidden" not in errors and "Traceback" not in errors
