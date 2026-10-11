# SPDX-License-Identifier: AGPL-3.0-only
"""Isolated configuration/SDK tests. No persistent listeners or paid model calls."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DEPLOYMENT = BACKEND.parent / "deployment" / "controls"


def profile_env(provider="local_stub"):
    env = dict(os.environ)
    env.update(
        PROVIDER=provider,
        LLM_BILLING_MODE="unmetered" if provider == "local_stub" else "metered",
        CONTROLS_DEPLOYMENT_ID="isolated-controlled-tests",
        TUTOR_PACK="datascience",
        DIALOGUE_ENABLED="1",
        DIALOGUE_POLICY_ID="isolated-test-only",
        DIALOGUE_RETENTION_SECONDS="3600",
        DIALOGUE_BACKUP_MAX_AGE_SECONDS="3600",
        OPENAI_BASE_URL="https://sdk.invalid/v1",
        OPENAI_API_KEY="fake-test-key",
        MODEL_FAST="test-fast",
        MODEL_STRONG="test-strong",
        OPENAI_THINKING_MODE="",
        OPENAI_RESPONSE_FORMAT="json_object",
        OPENAI_FINAL_CONTENT_ONLY="1",
        OPENAI_REASONING="0",
        ANTHROPIC_API_KEY="fake-test-key",
        ANTHROPIC_THINKING="0",
        ANTHROPIC_MODEL_FAST="test-anthropic-fast",
        ANTHROPIC_MODEL_STRONG="test-anthropic-strong",
        LLM_TIMEOUT_SECONDS="12",
        CONTROLS_INFERENCE_WINDOW_SECONDS="0",
        CONTROLS_INFERENCE_EXPIRES_AT="0",
    )
    return env


def command(directory, action, *, env=None, policy=None):
    args = [sys.executable, "-m", "app.controlled_runtime", action, "--data-dir", str(directory)]
    if policy:
        args.extend(["--policy", str(policy)])
    return subprocess.run(
        args, cwd=BACKEND, env=env or profile_env(), capture_output=True, text=True, timeout=30
    )


@pytest.fixture
def installation(tmp_path):
    import socket

    directory = tmp_path / "controlled-installation"
    policy = priced_policy(tmp_path)
    result = command(directory, "prepare", policy=policy)
    assert result.returncode == 0, result.stdout + result.stderr
    # Never probe the user's actual 8004/5177 runtime in stopped-host tests.
    path = directory / "runtime.json"
    manifest = json.loads(path.read_text())
    with socket.socket() as api, socket.socket() as frontend:
        api.bind(("127.0.0.1", 0))
        frontend.bind(("127.0.0.1", 0))
        manifest["api_port"] = api.getsockname()[1]
        manifest["frontend_port"] = frontend.getsockname()[1]
    manifest["frontend_origin"] = f"http://127.0.0.1:{manifest['frontend_port']}"
    path.write_text(json.dumps(manifest))
    return directory, policy


def priced_policy(directory):
    path = directory / "test-policy.json"
    policy = json.loads((DEPLOYMENT / "controlled-runtime-policy.example.json").read_text())
    policy.update(input_price=1, output_price=2, price_version="test-bounded-v1")
    path.write_text(json.dumps(policy))
    return path


def hashes(directory):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.iterdir()
        if p.is_file() and p.name != "launcher.lock"
    }


def test_prepare_check_never_reset_database_keys_grants_or_budget(installation):
    directory, policy = installation
    before = hashes(directory)
    checked = command(directory, "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert json.loads(checked.stdout)["schema_initialized_at_start"] is False
    assert hashes(directory) == before
    checked = command(
        directory, "check", env={**profile_env(), "CONTROLS_INFERENCE_WINDOW_SECONDS": "3600"}
    )
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["inference_window"] == {"state": "unarmed", "seconds": 3600}
    assert hashes(directory) == before
    repeated = command(directory, "prepare", policy=policy)
    assert repeated.returncode == 1 and hashes(directory) == before
    migrated = command(directory, "migrate", policy=policy)
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr
    after = hashes(directory)
    for name in (
        "authorization.json",
        "execution.key",
        "identity-private.pem",
        "public-key.pem",
        "runtime.json",
        "deletions.jsonl",
    ):
        assert before[name] == after[name]


def test_missing_database_schema_or_deletion_fence_fails_check_without_recreation(installation):
    import sqlite3

    directory, _ = installation
    fence = directory / "deletions.jsonl"
    original = fence.read_bytes()
    fence.unlink()
    assert command(directory, "check").returncode == 1 and not fence.exists()
    fence.write_bytes(original)
    db = directory / "belay.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("drop table control_data")
    conn.close()
    before = hashes(directory)
    assert command(directory, "check").returncode == 1
    assert hashes(directory) == before
    db.unlink()
    assert command(directory, "check").returncode == 1 and not db.exists()


def test_revoked_authorization_survives_checks_and_migration(installation):
    directory, policy = installation
    path = directory / "authorization.json"
    auth = json.loads(path.read_text())
    auth["subjects"] = {}
    path.write_text(json.dumps(auth))
    expected = path.read_bytes()
    assert command(directory, "check").returncode == 0
    assert command(directory, "migrate", policy=policy).returncode == 0
    assert path.read_bytes() == expected


@pytest.mark.parametrize(
    "changes",
    [
        {"PROVIDER": "bedrock"},
        {"PROVIDER": "unknown"},
        {"LLM_BILLING_MODE": ""},
        {"LLM_TIMEOUT_SECONDS": "nan"},
        {"PROVIDER": "openai_compatible", "OPENAI_THINKING_MODE": "unsupported"},
        {"PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""},
        {"PROVIDER": "openai_compatible", "OPENAI_BASE_URL": "http://remote.invalid/v1"},
    ],
)
def test_invalid_profiles_rejected_before_creating_any_data(tmp_path, changes):
    env = profile_env()
    env.update(changes)
    directory = tmp_path / "invalid-profile"
    result = command(
        directory, "prepare", env=env, policy=DEPLOYMENT / "controlled-runtime-policy.example.json"
    )
    assert result.returncode == 1 and not directory.exists()
    assert "fake-test-key" not in result.stdout + result.stderr


def test_metered_zero_price_rejected_and_policy_update_never_resets_on_migrate(
    installation, tmp_path
):
    directory, original = installation
    policy = json.loads(original.read_text())
    policy["input_price"] = 0
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    invalid = tmp_path / "zero-price-profile"
    assert (
        command(invalid, "prepare", env=profile_env("openai_compatible"), policy=path).returncode
        == 1
    )
    assert not invalid.exists()
    before = hashes(directory)
    result = command(directory, "migrate", policy=path)
    assert result.returncode == 1
    assert hashes(directory)["belay.sqlite3"] == before["belay.sqlite3"]


def test_stop_requires_matching_installation_and_never_kills_by_pid(installation):
    directory, _ = installation
    manifest = json.loads((directory / "runtime.json").read_text())
    receipt = directory / "running.json"
    receipt.write_text(json.dumps({"nonce": "other-installation", "pid": os.getpid()}))
    assert command(directory, "stop").returncode == 1
    assert not (directory / "stop.request").exists()
    receipt.write_text(json.dumps({"nonce": manifest["nonce"], "pid": os.getpid()}))
    # A stale receipt is not a live host. Only a matching installation lock
    # authorizes a cooperative stop signal, never a PID kill.
    assert command(directory, "stop").returncode == 1
    from app.local_dev import lock_directory

    with lock_directory(directory):
        result = command(directory, "stop")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"stop_requested": True, "stopped": False}
    assert (directory / "stop.request").exists()


@pytest.mark.parametrize("provider", ["openai_compatible", "anthropic", "local_stub"])
def test_same_prepared_installation_selects_existing_provider_from_environment(
    installation, provider
):
    directory, _ = installation
    before = hashes(directory)
    result = command(directory, "check", env=profile_env(provider))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["provider"] == provider
    assert hashes(directory) == before


@pytest.mark.parametrize("provider", ["openai_compatible", "anthropic", "local_stub"])
def test_real_registered_adapter_saved_unsaved_run_recovery_auth_and_accounting(tmp_path, provider):
    directory = tmp_path / "sdk-controlled-installation"
    env = profile_env(provider)
    prepared = command(directory, "prepare", env=env, policy=priced_policy(tmp_path))
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    # SDK-shaped responses through the REAL selected adapter, actual ASGI auth,
    # local runner, queue, worker, R2 same-DB publication and budget ledger.
    script = Path(__file__).with_name("controlled_runtime_scenario.py")
    tested = subprocess.run(
        [sys.executable, str(script), str(directory)],
        cwd=BACKEND,
        env={**env, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert tested.returncode == 0, tested.stdout + tested.stderr
    result = json.loads(tested.stdout)
    assert result["provider"] == provider
    assert result["checks"] >= 20 and result["real_network_calls"] == 0


@pytest.mark.parametrize("provider", ["anthropic", "local_stub"])
def test_other_providers_ignore_openai_specific_capability_configuration(installation, provider):
    directory, _ = installation
    env = profile_env(provider)
    env.update(OPENAI_THINKING_MODE="not-an-openai-capability", OPENAI_RESPONSE_FORMAT="invalid")
    result = command(directory, "check", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["provider"] == provider


@pytest.mark.parametrize("stop_reason", ["operator", "worker_failed"])
def test_managed_start_stop_lifecycle_without_listeners_or_model(
    monkeypatch, tmp_path, capsys, stop_reason
):
    import threading
    import time
    from contextlib import nullcontext
    from types import SimpleNamespace as NS

    from app import controlled_runtime as runtime
    from app.controls import jobs_worker

    events = []
    manifest = {"api_port": 8004, "frontend_port": 5177, "nonce": "test-installation"}
    monkeypatch.setattr(runtime, "load", lambda _: manifest)
    monkeypatch.setattr(runtime, "check", lambda _: {"checked": True})
    monkeypatch.setattr(runtime, "lock_directory", lambda _: nullcontext())
    monkeypatch.setattr(runtime, "check_loopback_port", lambda _: None)
    monkeypatch.setattr(
        runtime,
        "runtime_host",
        lambda *_: NS(
            handler=lambda _: object(),
            backend_origin="http://127.0.0.1:8004",
            origin="http://127.0.0.1:5177",
        ),
    )
    monkeypatch.setitem(sys.modules, "app.main", NS(app=object()))

    class Socket:
        def bind(self, address):
            events.append("bound")

        def listen(self, limit):
            pass

        def close(self):
            events.append("socket_closed")

    class Frontend:
        def __init__(self, *args):
            self.stopped = threading.Event()

        def serve_forever(self):
            self.stopped.wait(5)

        def shutdown(self):
            self.stopped.set()

        def server_close(self):
            events.append("frontend_closed")

    def worker():
        stopped = threading.Event()
        thread = threading.Thread(
            target=lambda: stopped.wait(5) if stop_reason == "operator" else None
        )
        thread.start()
        if stop_reason == "worker_failed":
            thread.join(1)
        return stopped, thread

    class Server:
        should_exit = False
        started = False

        def __init__(self, config):
            pass

        def run(self, **kwargs):
            if stop_reason == "operator":
                self.started = True
                time.sleep(0.3)  # Allow the supervisor to observe API readiness.
                (tmp_path / "stop.request").touch()
            deadline = time.monotonic() + 2
            while not self.should_exit and time.monotonic() < deadline:
                time.sleep(0.01)
            assert self.should_exit
            events.append("server_stopped")

    monkeypatch.setattr(runtime, "socket", NS(socket=Socket))
    monkeypatch.setattr(runtime, "ThreadingHTTPServer", Frontend)
    monkeypatch.setattr(runtime.uvicorn, "Server", Server)
    monkeypatch.setattr(jobs_worker, "start_worker", worker)
    assert runtime.start(tmp_path) == {"stopped": True}
    assert set(events) == {"bound", "socket_closed", "frontend_closed", "server_stopped"}
    assert not (tmp_path / "running.json").exists() and not (tmp_path / "stop.request").exists()
    output = capsys.readouterr().out
    assert "checked" in output
    assert ('"ready": true' in output) == (stop_reason == "operator")


def test_missing_start_does_not_create_a_directory(tmp_path):
    from app.controlled_runtime import start

    missing = tmp_path / "unprepared-installation"
    with pytest.raises(FileNotFoundError):
        start(missing)
    assert not missing.exists()


def test_managed_worker_cleans_saved_history_when_saving_off_and_exposes_fatal_exit(
    monkeypatch, caplog
):
    from types import SimpleNamespace as NS

    from app.controls import jobs_worker
    from app.conversations import repository

    events = []
    engine = object()
    store = NS(ledger=NS(engine=engine), admission=object())
    monkeypatch.setattr(jobs_worker.settings, "dialogue_enabled", False)
    monkeypatch.setattr(jobs_worker.settings, "store_backend", "memory")
    monkeypatch.setattr(jobs_worker, "execution_store", lambda: store)
    monkeypatch.setattr(jobs_worker, "ConsentRouter", lambda _: object())
    monkeypatch.setattr(jobs_worker, "get_active_pack", lambda: object())
    monkeypatch.setattr(
        jobs_worker,
        "AskAdapter",
        lambda *_: NS(cleanup=lambda: events.append("controls_cleanup")),
    )

    def history(selected_engine, policy):
        assert selected_engine is engine and not policy.enabled
        return NS(cleanup=lambda: events.append("dialogue_cleanup"))

    def fatal(*_):
        events.append("claim")
        raise RuntimeError("private provider or learner diagnostic")

    monkeypatch.setattr(repository, "ConversationStore", history)
    monkeypatch.setattr(jobs_worker, "run_one", fatal)
    stopped, thread = jobs_worker.start_worker()
    thread.join(timeout=3)
    stopped.set()
    assert not thread.is_alive()
    assert events == ["controls_cleanup", "dialogue_cleanup", "claim"]
    assert "controlled_worker_stopped" in caplog.text
    assert "private provider or learner diagnostic" not in caplog.text


def test_explicit_stub_profile_overrides_inherited_paid_provider_without_persisting_secret(
    tmp_path,
):
    env = profile_env("anthropic")
    directory = tmp_path / "explicit-stub-installation"
    file = DEPLOYMENT / "controlled-runtime.env.example"
    args = [
        sys.executable,
        "-m",
        "app.controlled_runtime",
        "prepare",
        "--data-dir",
        str(directory),
        "--env-file",
        str(file),
        "--policy",
        str(DEPLOYMENT / "controlled-runtime-policy.example.json"),
    ]
    result = subprocess.run(args, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    checked = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.controlled_runtime",
            "check",
            "--data-dir",
            str(directory),
            "--env-file",
            str(file),
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert checked.returncode == 0
    assert json.loads(checked.stdout)["provider"] == "local_stub"
    assert json.loads(checked.stdout)["models"] is None
    assert all(b"fake-test-key" not in p.read_bytes() for p in directory.iterdir() if p.is_file())


def test_supplemental_credentials_do_not_override_runtime(monkeypatch, tmp_path):
    from app.controlled_runtime import load_environment

    for key in ("OPENAI_API_KEY", "LLM_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROVIDER", "local_stub")
    config = tmp_path / "runtime.env"
    secret = tmp_path / "credentials.env"
    config.write_text("PROVIDER=openai_compatible\n")
    secret.write_text("OPENAI_API_KEY=test-file-key\nPROVIDER=wrong\nDATABASE_URL=wrong\n")
    load_environment(config, secret)
    assert os.environ["OPENAI_API_KEY"] == "test-file-key"
    assert os.environ["PROVIDER"] == "openai_compatible"
    assert os.environ.get("DATABASE_URL") != "wrong"
    monkeypatch.setenv("OPENAI_API_KEY", "test-process-key")
    load_environment(config, secret)
    assert os.environ["OPENAI_API_KEY"] == "test-process-key"


@pytest.mark.parametrize("fail_manifest", [False, True])
def test_explicit_incremental_authorization_is_idempotent_and_never_prepares(
    installation, tmp_path, fail_manifest
):
    import sqlite3

    directory, old_policy = installation
    seed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from pathlib import Path
from app.controlled_runtime import load
manifest=load(Path(__import__('sys').argv[1]))
from app.controls.ledger import Ledger
from app.controls.contracts import Scope, Amount
from app.store.db import engine
ledger=Ledger(engine)
scope=Scope(manifest['deployment'],'test-school','test-class','test-learner')
ledger.reserve('old-spend','old-task',scope,Amount(microunits=25),'model')
ledger.settle('old-spend',Amount(microunits=25))
ledger.reserve('old-unknown','unknown-task',scope,Amount(microunits=7),'model')
ledger.settle('old-unknown',None)
""",
            str(directory),
        ],
        cwd=BACKEND,
        env=profile_env(),
        capture_output=True,
        text=True,
    )
    assert seed.returncode == 0, seed.stdout + seed.stderr
    manifest_path = directory / "runtime.json"
    manifest = json.loads(manifest_path.read_text())
    import socket

    for port_field in ("api_port", "frontend_port"):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            manifest[port_field] = sock.getsockname()[1]
    manifest["inference_window"] = {"started": 100, "expires": 3700, "total_microunits": 50}
    manifest_path.write_text(json.dumps(manifest))
    policy = json.loads(old_policy.read_text())
    policy["version"] = "incremental-approved-v2"
    for level in ("deployment", "institution", "classroom", "learner"):
        policy[level]["microunits"] = 100025
    approved_policy = tmp_path / "incremental-policy.json"
    approved_policy.write_text(json.dumps(policy))
    grant = tmp_path / "authorization.json"
    grant.write_text(
        json.dumps(
            {
                "id": "explicit-two-hour-grant",
                "additional_microunits": 100000,
                "seconds": 7200,
                "unused_balance": "forfeit",
                "expected_consumed_microunits": 25,
                "expected_policy_version": json.loads(old_policy.read_text())["version"],
            }
        )
    )
    before = hashes(directory)
    args = [
        sys.executable,
        "-m",
        "app.controlled_runtime",
        "authorize-window",
        "--data-dir",
        str(directory),
        "--policy",
        str(approved_policy),
        "--authorization",
        str(grant),
    ]
    if fail_manifest:
        crashed = subprocess.run(
            [
                sys.executable,
                "-c",
                """
from pathlib import Path
from unittest.mock import patch
from app.controlled_runtime import authorize_window
import sys
with patch('app.controlled_runtime.os.replace',side_effect=OSError('simulated manifest failure')):
    authorize_window(*map(Path,sys.argv[1:]))
""",
                str(directory),
                str(approved_policy),
                str(grant),
            ],
            cwd=BACKEND,
            env=profile_env(),
            capture_output=True,
            text=True,
        )
        assert crashed.returncode != 0 and "simulated manifest failure" in crashed.stderr
        assert "pending_authorization" not in json.loads(manifest_path.read_text())
        with sqlite3.connect(directory / "belay.sqlite3") as conn:
            installed = json.loads(
                conn.execute("select policy from control_configuration").fetchone()[0]
            )
            assert installed["version"] == policy["version"]
    first = subprocess.run(args, cwd=BACKEND, env=profile_env(), capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    assert json.loads(first.stdout)["held_microunits"] == 7
    assert json.loads(first.stdout)["total_microunits"] == 100025
    saved = json.loads(manifest_path.read_text())
    assert "inference_window" not in saved
    assert saved["pending_authorization"]["seconds"] == 7200
    assert saved["authorization_history"][0]["previous_window"] == manifest["inference_window"]
    again = subprocess.run(args, cwd=BACKEND, env=profile_env(), capture_output=True, text=True)
    assert again.returncode == 0 and json.loads(again.stdout)["unchanged"] is True
    assert len(json.loads(manifest_path.read_text())["authorization_history"]) == 1
    after = hashes(directory)
    for name in before:
        if name not in ("runtime.json", "belay.sqlite3"):
            assert before[name] == after[name]
    with sqlite3.connect(directory / "belay.sqlite3") as conn:
        assert conn.execute("select count(*) from control_attempts").fetchone()[0] == 2
        assert (
            conn.execute("select state from control_attempts where id='old-unknown'").fetchone()[0]
            == "unknown"
        )
    checked = command(directory, "check")
    assert checked.returncode == 0, checked.stdout
    assert json.loads(checked.stdout)["inference_window"] == {"state": "unarmed", "seconds": 7200}
    grant_data = json.loads(grant.read_text())
    grant_data["additional_microunits"] = 200000
    grant.write_text(json.dumps(grant_data))
    rejected = subprocess.run(args, cwd=BACKEND, env=profile_env(), capture_output=True, text=True)
    assert rejected.returncode == 1


def test_check_expired_window_reports_blocker_without_changing_installation(installation):
    directory, _ = installation
    path = directory / "runtime.json"
    manifest = json.loads(path.read_text())
    manifest["inference_window"] = {"started": 100, "expires": 3700, "total_microunits": 100}
    path.write_text(json.dumps(manifest))
    before = hashes(directory)
    result = command(directory, "check")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["blockers"] == ["inference_window_expired"]
    assert report["start_allowed"] is False
    assert report["jobs_by_state"] == {}
    assert report["unknown_work_replayed"] is False
    assert hashes(directory) == before


def test_amount_only_transition_preserves_installation_and_pins_old_cap(installation):
    import sqlite3

    directory, _ = installation
    path = directory / "runtime.json"
    manifest = json.loads(path.read_text())
    old_window = {"started": 100, "expires": 3700, "total_microunits": 100}
    manifest["inference_window"] = old_window
    path.write_text(json.dumps(manifest))
    (directory / "running.json").write_text(
        json.dumps({"nonce": manifest["nonce"], "pid": 99999999})
    )
    seed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from app.controlled_runtime import load
m=load(Path(sys.argv[1]))
from app.controls.ledger import Ledger
from app.controls.contracts import Scope, Amount
from app.store.db import engine
l=Ledger(engine)
s=Scope(m['deployment'],'school','class','learner')
l.reserve('spent','old-task',s,Amount(microunits=25),'model')
l.settle('spent',Amount(microunits=25))
l.reserve('held','unknown-task',s,Amount(microunits=7),'model')
l.settle('held',None)
""",
            str(directory),
        ],
        cwd=BACKEND,
        env=profile_env(),
        capture_output=True,
        text=True,
    )
    assert seed.returncode == 0, seed.stdout + seed.stderr
    with sqlite3.connect(directory / "belay.sqlite3") as conn:
        conn.execute(
            "INSERT INTO control_jobs "
            "(id,operation,scopes,fingerprint,payload_bytes,state,created,expires,fence,sequence) "
            "VALUES (?,?,?, ?,0,'unknown',1,2,0,1)",
            ("u" * 64, "original-unknown", "{}", "f" * 64),
        )
    before = hashes(directory)
    env = {
        **profile_env(),
        "CONTROLS_INFERENCE_WINDOW_SECONDS": "7200",
        "CONTROLS_INFERENCE_TOTAL_MICROUNITS": "999999",
    }
    result = command(directory, "use-amount-only-budget", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["inference_total_microunits"] == 100
    assert report["model_calls"] == 0 and report["additional_microunits"] == 0
    assert report["stale_receipt_retained"] is True
    saved = json.loads(path.read_text())
    assert saved["budget_mode_history"][0]["previous_window"] == old_window
    assert saved["amount_only_budget"] == {"total_microunits": 100}
    assert "inference_window" not in saved
    assert all(
        hashes(directory)[name] == value for name, value in before.items() if name != "runtime.json"
    )
    after = hashes(directory)
    repeated = command(directory, "use-amount-only-budget", env=env)
    assert repeated.returncode == 0 and json.loads(repeated.stdout)["unchanged"] is True
    checked = command(directory, "check", env=env)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    report = json.loads(checked.stdout)
    assert report["inference_window"] == {"state": "disabled", "mode": "amount_only"}
    assert report["inference_total_microunits"] == 100
    assert report["jobs_by_state"] == {"unknown": 1}
    assert report["unknown_work_replayed"] is False
    assert hashes(directory) == after


def test_amount_only_failed_atomic_write_keeps_old_deadline(installation):
    directory, _ = installation
    path = directory / "runtime.json"
    manifest = json.loads(path.read_text())
    manifest["inference_window"] = {"started": 100, "expires": 3700, "total_microunits": 100}
    path.write_text(json.dumps(manifest))
    before = hashes(directory)
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from unittest.mock import patch
from app.controlled_runtime import use_amount_only_budget
with patch('app.controlled_runtime.os.replace',side_effect=OSError('simulated write failure')):
    use_amount_only_budget(Path(sys.argv[1]))
""",
            str(directory),
        ],
        cwd=BACKEND,
        env=profile_env(),
        capture_output=True,
        text=True,
    )
    assert crashed.returncode != 0 and "simulated write failure" in crashed.stderr
    assert hashes(directory) == before
    assert json.loads(command(directory, "check").stdout)["blockers"] == [
        "inference_window_expired"
    ]


def test_amount_only_requires_exclusive_host_lock(installation):
    from app.local_dev import lock_directory

    directory, _ = installation
    before = hashes(directory)
    with lock_directory(directory):
        rejected = command(directory, "use-amount-only-budget")
    assert rejected.returncode == 1
    assert hashes(directory) == before


@pytest.mark.parametrize(
    "blocker", ["queued", "running", "cancel_requested", "receipt", "pending", "missing_cap"]
)
def test_amount_only_rejects_unsafe_transitions_without_mutation(installation, blocker):
    import sqlite3

    directory, _ = installation
    path = directory / "runtime.json"
    manifest = json.loads(path.read_text())
    manifest["inference_window"] = {"started": 100, "expires": 3700}
    if blocker != "missing_cap":
        manifest["inference_window"]["total_microunits"] = 100
    if blocker == "pending":
        manifest.pop("inference_window")
        manifest["pending_authorization"] = {"seconds": 3600, "total_microunits": 100}
    path.write_text(json.dumps(manifest))
    if blocker == "receipt":
        (directory / "running.json").write_text("{}")
    if blocker in {"queued", "running", "cancel_requested"}:
        with sqlite3.connect(directory / "belay.sqlite3") as conn:
            conn.execute(
                "INSERT INTO control_jobs "
                "(id,operation,scopes,fingerprint,payload_bytes,state,created,expires,fence,sequence) "
                "VALUES (?,?,?, ?,0,?,1,2,0,1)",
                ("a" * 64, "old-active", "{}", "f" * 64, blocker),
            )
    before = hashes(directory)
    result = command(directory, "use-amount-only-budget")
    assert result.returncode == 1
    assert hashes(directory) == before


def test_new_amount_only_profile_requires_and_persists_finite_cap(installation):
    directory, _ = installation
    result = command(
        directory,
        "use-amount-only-budget",
        env={**profile_env(), "CONTROLS_INFERENCE_TOTAL_MICROUNITS": "200"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(command(directory, "check").stdout)
    assert report["inference_total_microunits"] == 200
    assert report["inference_window"]["mode"] == "amount_only"


@pytest.mark.parametrize("fail_manifest", [False, True])
def test_amount_only_grant_is_explicit_retryable_and_preserves_old_spend(
    installation, fail_manifest
):
    import sqlite3

    directory, policy_path = installation
    result = command(
        directory,
        "use-amount-only-budget",
        env={**profile_env(), "CONTROLS_INFERENCE_TOTAL_MICROUNITS": "100"},
    )
    assert result.returncode == 0
    manifest = json.loads((directory / "runtime.json").read_text())
    old_policy = json.loads(policy_path.read_text())
    seed = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from app.controlled_runtime import load
m=load(Path(sys.argv[1]))
from app.controls.ledger import Ledger
from app.controls.contracts import Scope,Amount
from app.store.db import engine
l=Ledger(engine);s=Scope(m['deployment'],'school','class','learner')
l.reserve('spent','old-task',s,Amount(microunits=25),'model');l.settle('spent',Amount(microunits=25))
l.reserve('unknown','old-unknown',s,Amount(microunits=7),'model');l.settle('unknown',None)
""",
            str(directory),
        ],
        cwd=BACKEND,
        env=profile_env(),
        capture_output=True,
        text=True,
    )
    assert seed.returncode == 0, seed.stderr
    grant_policy = {
        **old_policy,
        "version": "amount-grant-v2",
        "model_quotas": {
            "short_period_seconds": 21600,
            "short_anchor_utc": 57600,
            "short_microunits": 100,
            "week_anchor_utc": 316800,
            "week_microunits": 150,
        },
    }
    for level in ("deployment", "institution", "classroom", "learner"):
        grant_policy[level] = {**old_policy[level], "microunits": 150}
    target = directory.parent / "proposed-policy.json"
    target.write_text(json.dumps(grant_policy))
    auth = directory.parent / "approved-test-grant.json"
    auth_body = {
        "id": "isolated-explicit-grant",
        "additional_microunits": 50,
        "expected_total_microunits": 100,
        "expected_policy_version": old_policy["version"],
        "expected_deployment_id": manifest["deployment"],
        "unused_balance": "retain",
    }
    auth.write_text(json.dumps(auth_body))
    before = hashes(directory)
    args = [
        sys.executable,
        "-m",
        "app.controlled_runtime",
        "authorize-budget",
        "--data-dir",
        str(directory),
        "--policy",
        str(target),
        "--authorization",
        str(auth),
    ]
    if fail_manifest:
        crashed = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import sys
from pathlib import Path
from unittest.mock import patch
from app.controlled_runtime import authorize_budget
with patch('app.controlled_runtime.os.replace', side_effect=OSError('simulated grant write failure')):
    authorize_budget(*map(Path,sys.argv[1:]))
""",
                str(directory),
                str(target),
                str(auth),
            ],
            cwd=BACKEND,
            env=profile_env(),
            capture_output=True,
            text=True,
        )
        assert crashed.returncode != 0 and "simulated grant write failure" in crashed.stderr
        assert (
            json.loads((directory / "runtime.json").read_text())["amount_only_budget"][
                "total_microunits"
            ]
            == 100
        )
    first = subprocess.run(args, cwd=BACKEND, env=profile_env(), capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    assert json.loads(first.stdout)["total_microunits"] == 150
    saved = hashes(directory)
    again = subprocess.run(args, cwd=BACKEND, env=profile_env(), capture_output=True, text=True)
    assert again.returncode == 0 and json.loads(again.stdout)["unchanged"] is True
    assert hashes(directory) == saved
    for name in before:
        if name not in ("runtime.json", "belay.sqlite3"):
            assert before[name] == saved[name]
    with sqlite3.connect(directory / "belay.sqlite3") as conn:
        rows = conn.execute("select state,actual,reserved from control_attempts").fetchall()
        assert len(rows) == 2
        assert (
            sum(json.loads(a)["microunits"] for s, a, r in rows if a and json.loads(a) is not None)
            == 25
        )
        assert sum(json.loads(r)["microunits"] for s, a, r in rows if s == "unknown") == 7
    auth_body["additional_microunits"] = 100
    auth.write_text(json.dumps(auth_body))
    conflict = subprocess.run(args, cwd=BACKEND, env=profile_env(), capture_output=True, text=True)
    assert conflict.returncode == 1 and hashes(directory) == saved


def test_check_counts_old_queued_and_unknown_work_without_replay(installation):
    import sqlite3

    directory, _ = installation
    with sqlite3.connect(directory / "belay.sqlite3") as conn:
        for index, state in enumerate(("queued", "unknown")):
            conn.execute(
                "INSERT INTO control_jobs "
                "(id,operation,scopes,fingerprint,payload_bytes,state,created,expires,fence,sequence) "
                "VALUES (?,?,?, ?,0,?,1,2,0,?)",
                (str(index) * 64, "old-" + state, "{}", "f" * 64, state, index),
            )
    before = hashes(directory)
    result = command(directory, "check")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["jobs_by_state"] == {"queued": 1, "unknown": 1}
    assert report["queued_work_may_execute"] is True
    assert report["unknown_work_replayed"] is False
    assert hashes(directory) == before  # No expiry processing or dispatch in check.


def test_duplicate_start_is_rejected_before_preflight_or_dispatch(installation):
    from app.local_dev import lock_directory

    directory, _ = installation
    with lock_directory(directory):
        before = hashes(directory)
        result = command(directory, "start")
        assert result.returncode == 1
        assert json.loads(result.stdout)["error"] == "runtime_already_running_or_locked"
        assert hashes(directory) == before
    assert not (directory / "running.json").exists()


def test_occupied_port_aborts_before_window_activation_or_worker(monkeypatch, tmp_path):
    from types import SimpleNamespace as NS

    from app import controlled_runtime as runtime

    monkeypatch.setattr(runtime, "load", lambda _: {"api_port": 8004, "frontend_port": 5177})
    monkeypatch.setattr(runtime, "check", lambda _: {"checked": True})
    monkeypatch.setattr(runtime, "runtime_host", lambda *_: NS())

    def occupied(_):
        raise OSError("local port already has a listener")

    monkeypatch.setattr(runtime, "check_loopback_port", occupied)
    monkeypatch.setattr(runtime, "arm_inference_window", lambda *_: pytest.fail("must not arm"))
    with pytest.raises(OSError, match="listener"):
        runtime.start(tmp_path)
    assert not (tmp_path / "running.json").exists()


def test_root_powershell_wrappers_delegate_paths_without_preparing(tmp_path):
    import shutil

    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell unavailable")
    root = BACKEND.parent
    env = tmp_path / "runtime config.env"
    env.write_text("PROVIDER=local_stub\n")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("OPENAI_API_KEY=fake-unused\n")
    data = tmp_path / "data directory"
    # Stub only the Python command; execute the real PowerShell wrappers.
    # No runtime is started, no listener created, no provider constructed.
    script = tmp_path / "wrapper-check.ps1"
    script.write_text("""
param($Root, $EnvFile, $Credentials, $DataDir)
$ErrorActionPreference='Stop'
function python { $global:LASTEXITCODE=0; ConvertTo-Json -Compress -InputObject @($args) }
& (Join-Path $Root 'start-belay.ps1') -Check -EnvFile $EnvFile -CredentialsEnvFile $Credentials -DataDir $DataDir
& (Join-Path $Root 'start-belay.ps1') -EnvFile $EnvFile -CredentialsEnvFile $Credentials -DataDir $DataDir
& (Join-Path $Root 'stop-belay.ps1') -DataDir $DataDir
& (Join-Path $Root 'start-belay.ps1') -UseAmountOnlyBudget -EnvFile $EnvFile -CredentialsEnvFile $Credentials -DataDir $DataDir
& (Join-Path $Root 'start-belay.ps1') -BudgetAuthorization $EnvFile -BudgetPolicy $Credentials -EnvFile $EnvFile -CredentialsEnvFile $Credentials -DataDir $DataDir
""")
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(script),
            str(root),
            str(env),
            str(credentials),
            str(data),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    commands = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("[")]
    assert len(commands) == 5
    assert [c[2] for c in commands] == [
        "check",
        "start",
        "stop",
        "use-amount-only-budget",
        "authorize-budget",
    ]
    for c in commands:
        assert c[c.index("--data-dir") + 1] == str(data)
    assert "--prompt-missing-key" not in commands[0]
    assert "--prompt-missing-key" in commands[1]
    assert "--prompt-missing-key" not in commands[3]
    assert "--prompt-missing-key" not in commands[4]
    assert commands[4][commands[4].index("--authorization") + 1] == str(env)
    assert commands[4][commands[4].index("--policy") + 1] == str(credentials)
    assert commands[0][commands[0].index("--credentials-env-file") + 1] == str(credentials)
    assert not data.exists()
    env.unlink()
    missing = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-File",
            str(script),
            str(root),
            str(env),
            str(credentials),
            str(data),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert missing.returncode != 0 and "Runtime EnvFile is missing" in missing.stderr
    assert not data.exists()


def test_daily_default_paths_and_optional_credentials_are_checkout_relative(tmp_path):
    import shutil

    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell unavailable")
    checkout = tmp_path / "other checkout"
    for relative in ("start-belay.ps1", "deployment/controls/start-controlled-runtime.ps1"):
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND.parent / relative, target)
    (checkout / "backend").mkdir()
    config = checkout / "deployment/local/controlled-config/.env"
    config.parent.mkdir(parents=True)
    config.write_text("PROVIDER=local_stub\n")
    script = tmp_path / "check-defaults.ps1"
    script.write_text("""
param($Root)
$ErrorActionPreference='Stop'
function python { $global:LASTEXITCODE=0; ConvertTo-Json -Compress -InputObject @($args) }
Push-Location -LiteralPath $Root
try { & (Join-Path $Root 'start-belay.ps1') -Check -DataDir 'deployment/local/controlled-runtime' }
finally { Pop-Location }
""")

    def invoke():
        result = subprocess.run(
            [shell, "-NoProfile", "-File", str(script), str(checkout)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    no_credentials = invoke()
    assert no_credentials[no_credentials.index("--env-file") + 1] == str(config)
    assert no_credentials[no_credentials.index("--data-dir") + 1] == str(
        checkout / "deployment/local/controlled-runtime"
    )
    assert "--credentials-env-file" not in no_credentials
    (checkout / "backend/.env").write_text("OPENAI_API_KEY=fake-only\n")
    with_credentials = invoke()
    assert with_credentials[with_credentials.index("--credentials-env-file") + 1] == str(
        checkout / "backend/.env"
    )
    assert not (checkout / "deployment/local/controlled-runtime").exists()
