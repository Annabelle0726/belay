# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit loopback-only host for authenticated local demos (not a production issuer).

Run from backend/: python -m scripts.local_demo
The private key and access tokens stay in memory. Only the temporary public key
and synthetic grants are passed to a child backend, using its normal auth path.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.registry import get_active_pack

ISSUER = "http://belay-local-demo.invalid"
AUDIENCE = "belay-local-demo"
SUBJECT = "demo:12345"
LEARNER = "gh:12345"
INSTITUTION = "local-demo"
CLASS = "demo-class"
TOKEN_PATH = "/__belay_local_token"
PAGES = {"/dev-client.html", "/widget.html", "/embed-demo.html"}
BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"


class DemoIdentity:
    def __init__(self, directory: Path, pack):
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = self._key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.public_key_file = directory / "identity.pub"
        self.authorization_file = directory / "authorization.json"
        self.public_key_file.write_bytes(public_key)
        assignments = {
            ex["id"]: "local-" + pack.id + "-v1"
            for module in pack.curriculum()
            for ex in module["exercises"]
        }
        self.authorization_file.write_text(
            json.dumps(
                {
                    "exercise_versions": assignments,
                    "subjects": {
                        SUBJECT: [
                            {
                                "institution_id": INSTITUTION,
                                "class_id": CLASS,
                                "learner_id": LEARNER,
                                "assignments": assignments,
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

    def token(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": ISSUER, "aud": AUDIENCE, "sub": SUBJECT, "iat": now, "exp": now + 300},
            self._key,
            algorithm="RS256",
        )

    def backend_environment(self, frontend_port: int, pack_id: str) -> dict[str, str]:
        return {
            **os.environ,
            "BELAY_ENV": "local",
            "AUTH_ISSUER": ISSUER,
            "AUTH_AUDIENCE": AUDIENCE,
            "AUTH_PUBLIC_KEY_FILE": str(self.public_key_file),
            "AUTH_AUTHORIZATION_FILE": str(self.authorization_file),
            "STORE_BACKEND": "memory",
            "TUTOR_PACK": pack_id,
            "CORS_ORIGINS": f"http://127.0.0.1:{frontend_port},http://localhost:{frontend_port}",
        }


def bootstrap(backend_port: int) -> str:
    # No token/key is embedded in the page or URL. The host callback retrieves a
    # fresh five-minute token on demand, with a same-origin custom-header request.
    return f"""<script>
window.BELAY_AUTH_ORIGIN = "http://127.0.0.1:{backend_port}";
window.BELAY_LEARNER_ID = "{LEARNER}";
window.BELAY_INSTITUTION_ID = "{INSTITUTION}";
window.BELAY_CLASS_ID = "{CLASS}";
window.BELAY_GET_ACCESS_TOKEN = async () => {{
  const response = await fetch("{TOKEN_PATH}", {{
    headers: {{ "X-Belay-Local-Demo": "1" }}, cache: "no-store"
  }});
  if (!response.ok) throw new Error("Local demo credential request failed");
  return (await response.json()).access_token;
}};
</script>"""


class DemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, identity: DemoIdentity, backend_port: int, **kwargs):
        self.identity = identity
        self.backend_port = backend_port
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def log_message(self, format, *args):
        # Neither credentials nor arbitrary query strings are logged by this host.
        pass

    def _host_allowed(self) -> bool:
        address = self.server.server_address
        if not isinstance(address, tuple):
            return False
        port = address[1]
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _send(self, body: bytes, media_type: str):
        self.send_response(200)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_allowed():
            self.send_error(403, "Loopback host required")
            return
        url = urlsplit(self.path)
        if url.path == TOKEN_PATH:
            expected_origin = "http://" + self.headers["Host"]
            if (
                url.query
                or self.headers.get("X-Belay-Local-Demo") != "1"
                or self.headers.get("Origin", expected_origin) != expected_origin
                or self.headers.get("Sec-Fetch-Site", "same-origin") != "same-origin"
            ):
                self.send_error(403, "Same-origin demo request required")
                return
            self._send(
                json.dumps({"access_token": self.identity.token()}).encode(), "application/json"
            )
            return
        if url.path in PAGES:
            page = (FRONTEND / url.path.lstrip("/")).read_text(encoding="utf-8")
            page = page.replace(
                '<script src="auth-client.js">',
                bootstrap(self.backend_port) + '\n<script src="auth-client.js">',
            )
            page = page.replace(
                'value="http://localhost:8000"', f'value="http://127.0.0.1:{self.backend_port}"'
            )
            self._send(page.encode(), "text/html; charset=utf-8")
            return
        super().do_GET()

    def do_HEAD(self):
        if not self._host_allowed() or urlsplit(self.path).path == TOKEN_PATH:
            self.send_error(403)
            return
        super().do_HEAD()


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _wait_backend(process, port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("backend exited during startup")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("backend startup timed out")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=_port, default=5173)
    parser.add_argument("--backend-port", type=_port, default=8000)
    parser.add_argument("--pack", choices=["datascience", "_skeleton"], default="datascience")
    args = parser.parse_args()
    if args.frontend_port == args.backend_port:
        parser.error("frontend and backend ports must differ")
    # Do not connect the browser to a pre-existing backend with different identity config.
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.backend_port))
        except OSError:
            parser.error("backend port is busy; stop the existing server or select another port")
    os.environ["TUTOR_PACK"] = args.pack
    pack = get_active_pack()
    with tempfile.TemporaryDirectory(prefix="belay-local-demo-") as directory:
        identity = DemoIdentity(Path(directory), pack)
        handler = partial(DemoHandler, identity=identity, backend_port=args.backend_port)
        try:
            server = ThreadingHTTPServer(("127.0.0.1", args.frontend_port), handler)
        except OSError:
            parser.error("frontend port is busy; stop http.server or select another port")
        server.daemon_threads = True
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.backend_port),
        ]
        if (BACKEND / ".env").exists():
            command.extend(["--env-file", str(BACKEND / ".env")])
        process = None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            process = subprocess.Popen(
                command,
                cwd=str(BACKEND),
                env=identity.backend_environment(args.frontend_port, args.pack),
            )
            _wait_backend(process, args.backend_port)
            print(
                f"Local authenticated demo: http://127.0.0.1:{args.frontend_port}/dev-client.html"
            )
            print(
                "Loopback only; synthetic learner gh:12345; memory store; Ctrl+C stops both servers."
            )
            while process.poll() is None:
                time.sleep(0.3)
            raise RuntimeError("backend exited; local demo stopped")
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
