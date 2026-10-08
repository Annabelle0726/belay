# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit loopback-only demo host with real, short-lived signed credentials."""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO

import jwt
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2]
AUDIENCE = "belay-local-demo"
SUBJECT = "local-demo-learner"
LEARNER = "gh:12345"


def lock_directory(data_dir: Path) -> BinaryIO:
    """Prevent simultaneous launchers rotating the same key or touching its DB."""
    data_dir.mkdir(parents=True, exist_ok=True)
    handle = (data_dir / "launcher.lock").open("a+b")
    try:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise
    return handle


class DemoHost:
    def __init__(self, backend_origin: str):
        self.backend_origin = backend_origin
        self.origin = ""  # Set from the bound listener before accepting requests.
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def token(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": self.origin, "aud": AUDIENCE, "sub": SUBJECT, "iat": now, "exp": now + 300},
            self.key,
            algorithm="RS256",
        )

    def bootstrap(self) -> bytes:
        # Only public configuration goes into JS. Tokens are fetched on demand,
        # kept in memory and never inserted into HTML, URLs or browser storage.
        origin = json.dumps(self.backend_origin)
        return f"""'use strict';
window.BELAY_AUTH_ORIGIN = {origin};
window.SOL_BACKEND_URL = {origin};
window.BELAY_LEARNER_ID = '{LEARNER}';
window.BELAY_INSTITUTION_ID = 'local-demo';
window.BELAY_CLASS_ID = 'local-class';
window.BELAY_GET_ACCESS_TOKEN = async () => {{
  const response = await fetch('/__belay_local__/token', {{cache: 'no-store', credentials: 'omit'}});
  if (!response.ok) throw new Error('Local credential service unavailable');
  const data = await response.json();
  if (typeof data.access_token !== 'string') throw new Error('Invalid local credential response');
  return data.access_token;
}};
""".encode()

    def handler(self, directory: Path):
        host = self

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(directory), **kwargs)

            def log_message(self, format, *args):
                # No request paths, credentials, learner content or source in logs.
                pass

            def send_head(self):
                # Reject DNS rebinding and cross-site browser fetches, including
                # HTML/bootstrap loads. There is deliberately no token CORS grant.
                if (
                    self.headers.get("Host") != host.origin.removeprefix("http://")
                    or self.headers.get("Origin", host.origin) != host.origin
                    or self.headers.get("Sec-Fetch-Site", "none") not in {"none", "same-origin"}
                ):
                    self.send_error(403, "local origin required")
                    return None
                if self.path == "/__belay_local__/token":
                    if self.command != "GET":
                        self.send_error(405, "GET required")
                        return None
                    body = json.dumps({"access_token": host.token()}).encode()
                    content_type = "application/json"
                elif self.path == "/__belay_local__/bootstrap.js":
                    body = host.bootstrap()
                    content_type = "text/javascript"
                else:
                    path = Path(self.translate_path(self.path))
                    if path.name not in {"dev-client.html", "widget.html", "embed-demo.html"}:
                        return super().send_head()
                    try:
                        html = path.read_text(encoding="utf-8")
                    except OSError:
                        self.send_error(404)
                        return None
                    html = html.replace(
                        '<script src="auth-client.js"></script>',
                        '<script src="/__belay_local__/bootstrap.js"></script>\n'
                        '<script src="auth-client.js"></script>',
                    ).replace('value="http://localhost:8000"', f'value="{host.backend_origin}"')
                    body = html.encode()
                    content_type = "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                return io.BytesIO(body)

        return Handler


def configure(host: DemoHost, data_dir: Path, save_dialogue: bool) -> None:
    """Provision only separate local files; never reuse deployment auth or its DB."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if (data_dir / "demo.sqlite3").exists() and not (data_dir / "deletions.jsonl").exists():
        raise ValueError("existing local database requires its deletion ledger")
    public_key = data_dir / "public-key.pem"
    public_key.write_bytes(
        host.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    from .core.registry import get_active_pack

    versions = {
        exercise["id"]: "local-v1"
        for module in get_active_pack().curriculum()
        for exercise in module["exercises"]
    }
    authorization = data_dir / "authorization.json"
    authorization.write_text(
        json.dumps(
            {
                "exercise_versions": versions,
                "subjects": {
                    SUBJECT: [
                        {
                            "institution_id": "local-demo",
                            "class_id": "local-class",
                            "learner_id": LEARNER,
                            "assignments": versions,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    # Ignore inherited dialogue settings: the explicit local flag selects a
    # synthetic one-hour policy, never an institutional retention approval.
    for name in tuple(os.environ):
        if name.startswith("DIALOGUE_"):
            del os.environ[name]
    os.environ.update(
        BELAY_ENV="local",
        AUTH_ISSUER=host.origin,
        AUTH_AUDIENCE=AUDIENCE,
        AUTH_PUBLIC_KEY_FILE=str(public_key),
        AUTH_AUTHORIZATION_FILE=str(authorization),
        DATABASE_URL="sqlite:///" + (data_dir / "demo.sqlite3").as_posix(),
        STORE_BACKEND="sql",
        CORS_ORIGINS=host.origin,
        DIALOGUE_ENABLED="1" if save_dialogue else "0",
        DIALOGUE_POLICY_ID="local-test-only",
        DIALOGUE_RETENTION_SECONDS="3600",
        DIALOGUE_BACKUP_MAX_AGE_SECONDS="3600",
        DIALOGUE_DELETION_LEDGER_FILE=str(data_dir / "deletions.jsonl"),
    )
    # Delay all settings/engine imports until local environment is complete.
    from .conversations.ledger import DeletionLedger
    from .conversations.migration import migrate
    from .store.db import engine

    # Create once even with saving off, so later opt-in is possible; a missing
    # ledger alongside an existing DB must never be silently recreated.
    DeletionLedger(str(data_dir / "deletions.jsonl")).initialize()
    migrate(engine)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--env-file", type=Path, default=ROOT / "backend" / ".env")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "deployment" / "local")
    parser.add_argument("--save-dialogue", action="store_true")
    args = parser.parse_args(argv)
    if any(not 0 <= port <= 65535 for port in (args.api_port, args.frontend_port)):
        parser.error("ports must be between 0 and 65535")
    # Reserve both ports before touching configuration or local data. Do not kill
    # existing uvicorn/http.server processes or silently connect to another app.
    api_socket = socket.socket()
    frontend = None
    directory_lock = None
    try:
        try:
            api_socket.bind(("127.0.0.1", args.api_port))
            api_socket.listen(128)
            host = DemoHost(f"http://127.0.0.1:{api_socket.getsockname()[1]}")
            frontend = ThreadingHTTPServer(
                ("127.0.0.1", args.frontend_port), host.handler(ROOT / "frontend")
            )
        except OSError:
            parser.error("local ports unavailable; stop existing servers or choose other ports")
        host.origin = f"http://127.0.0.1:{frontend.server_port}"
        load_dotenv(args.env_file, override=False)
        try:
            directory_lock = lock_directory(args.data_dir.resolve())
            configure(host, args.data_dir.resolve(), args.save_dialogue)
        except (OSError, ValueError, HTTPException):
            parser.error(
                "local setup failed; check pack/configuration, local deletion ledger, "
                "and whether another launcher uses this data directory"
            )
        server = uvicorn.Server(
            uvicorn.Config("app.main:app", host="127.0.0.1", access_log=False, log_level="warning")
        )
        thread = threading.Thread(target=frontend.serve_forever, daemon=True)
        thread.start()
        print(f"Local demo: {host.origin}/dev-client.html", flush=True)
        print(f"Backend: {host.backend_origin}; dialogue saving: {args.save_dialogue}", flush=True)
        print("Local synthetic identity only. Ctrl+C stops both servers.", flush=True)
        try:
            server.run(sockets=[api_socket])
        finally:
            frontend.shutdown()
            thread.join(timeout=5)
    finally:
        if frontend is not None:
            frontend.server_close()
        api_socket.close()
        if directory_lock is not None:
            directory_lock.close()


if __name__ == "__main__":
    main()
