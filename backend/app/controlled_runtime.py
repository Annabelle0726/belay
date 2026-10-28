# SPDX-License-Identifier: AGPL-3.0-only
"""Environment-configured loopback host over Belay's existing controlled APIs.

prepare creates a NEW isolated local installation; migrate is explicit; start
only checks existing state before starting services. No inference probe is made;
the worker can then dispatch eligible queued jobs, never replay unknown jobs.
Institution-hosted identity and PostgreSQL deployments use the same app/worker
modules with operator provisioning, not this synthetic loopback credential host.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import socket
import sys
import threading
import time
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast

import jwt
import uvicorn
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from dotenv import dotenv_values

from .local_dev import (
    AUDIENCE,
    LEARNER,
    ROOT,
    SUBJECT,
    DemoHost,
    check_loopback_port,
    lock_directory,
)


class RuntimeHost(DemoHost):
    issuer: str

    def token(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {"iss": self.issuer, "aud": AUDIENCE, "sub": SUBJECT, "iat": now, "exp": now + 300},
            self.key,
            algorithm="RS256",
        )


def private_write(path: Path, body: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        os.write(fd, body)
    finally:
        os.close(fd)


def environment(directory: Path, manifest: dict) -> None:
    # Assembly-owned paths never inherit a real deployment DB/auth file. Model,
    # pack and dialogue policy remain explicitly selected by backend environment.
    url = "sqlite:///" + (directory / "belay.sqlite3").as_posix()
    os.environ.update(
        BELAY_ENV="local",
        STORE_BACKEND="sql",
        STORE_AUTO_CREATE="0",
        DATABASE_URL=url,
        CONTROLS_DATABASE_URL=url,
        CONTROLS_MODE="enforced",
        CONTROLS_JOBS_ENABLED="1",
        CONTROLS_DEPLOYMENT_ID=manifest["deployment"],
        CONTROLS_DATA_KEY_FILE=str(directory / "execution.key"),
        AUTH_ISSUER=manifest["issuer"],
        AUTH_AUDIENCE=AUDIENCE,
        AUTH_PUBLIC_KEY_FILE=str(directory / "public-key.pem"),
        AUTH_AUTHORIZATION_FILE=str(directory / "authorization.json"),
        CORS_ORIGINS=manifest["frontend_origin"],
        DIALOGUE_DELETION_LEDGER_FILE=str(directory / "deletions.jsonl"),
    )
    pending = manifest.get("pending_authorization")
    if pending:
        os.environ["CONTROLS_INFERENCE_WINDOW_SECONDS"] = str(pending["seconds"])
        os.environ["CONTROLS_INFERENCE_EXPIRES_AT"] = "0"
        os.environ["CONTROLS_INFERENCE_TOTAL_MICROUNITS"] = str(pending["total_microunits"])
    window = manifest.get("inference_window")
    if window is not None:
        # A persisted authorization cannot be renewed/disabled by env edits.
        validate_window(window)
        os.environ["CONTROLS_INFERENCE_EXPIRES_AT"] = str(window["expires"])
        if "total_microunits" in window:
            os.environ["CONTROLS_INFERENCE_TOTAL_MICROUNITS"] = str(window["total_microunits"])
    if "amount_only_budget" in manifest:
        cap = amount_only_cap(manifest)
        os.environ["CONTROLS_INFERENCE_WINDOW_SECONDS"] = "0"
        os.environ["CONTROLS_INFERENCE_EXPIRES_AT"] = "0"
        os.environ["CONTROLS_INFERENCE_TOTAL_MICROUNITS"] = str(cap)


def amount_only_cap(manifest: dict) -> int:
    cap = manifest["amount_only_budget"]["total_microunits"]
    if (
        type(cap) is not int
        or not 0 <= cap <= 10**15
        or manifest.get("inference_window") is not None
        or manifest.get("pending_authorization") is not None
    ):
        raise ValueError("invalid amount-only budget")
    return cap


def validate_window(window: dict) -> None:
    import math

    started, expires = window["started"], window["expires"]
    if not all(type(v) in {int, float} and math.isfinite(v) for v in (started, expires)):
        raise ValueError("invalid inference window")
    if not 0 < expires - started <= 7200:
        raise ValueError("invalid inference window duration")
    cap = window.get("total_microunits")
    if cap is not None and (type(cap) is not int or not 0 <= cap <= 10**15):
        raise ValueError("invalid inference window budget")


def arm_inference_window(directory: Path, manifest: dict) -> dict:
    from .config import settings

    if "amount_only_budget" in manifest:
        settings.controls_inference_total_microunits = amount_only_cap(manifest)
        settings.controls_inference_window_seconds = 0
        settings.controls_inference_expires_at = 0
        return manifest
    pending = manifest.get("pending_authorization")
    seconds = pending["seconds"] if pending else settings.controls_inference_window_seconds
    if not 0 <= seconds <= 7200:
        raise ValueError("inference window seconds must be between 0 and 7200")
    window = manifest.get("inference_window")
    if window is None and seconds:
        now = time.time()
        window = {"started": now, "expires": now + seconds}
        cap = (
            pending["total_microunits"] if pending else settings.controls_inference_total_microunits
        )
        if cap is not None:
            window["total_microunits"] = cap
        if pending:
            window["authorization_id"] = pending["id"]
        manifest = {**manifest, "inference_window": window}
        manifest.pop("pending_authorization", None)
        temporary = directory / ("runtime-" + uuid.uuid4().hex + ".pending")
        try:
            private_write(temporary, json.dumps(manifest, indent=2).encode())
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, directory / "runtime.json")
        finally:
            temporary.unlink(missing_ok=True)
    if window is not None:
        validate_window(window)
        if time.time() >= window["expires"]:
            raise ValueError("inference authorization expired; explicit review required")
        settings.controls_inference_expires_at = float(window["expires"])
        if "total_microunits" in window:
            settings.controls_inference_total_microunits = window["total_microunits"]
    return manifest


def validate_provider() -> None:
    from importlib.util import find_spec

    from .agent.llm import _timeout, provider_class
    from .config import settings

    provider_class(settings.provider)  # Selection only, never construct an SDK.
    if settings.provider not in {"openai_compatible", "anthropic", "local_stub"}:
        raise ValueError("provider is not implemented for controlled execution")
    _timeout()
    sdk_module = {"openai_compatible": "openai", "anthropic": "anthropic"}.get(settings.provider)
    if sdk_module and find_spec(sdk_module) is None:
        raise ValueError("selected provider SDK must be installed")
    if settings.provider == "openai_compatible":
        from urllib.parse import urlsplit

        if settings.openai_thinking_mode not in {
            "",
            "enabled",
            "disabled",
        } or settings.openai_response_format not in {"json_object", "none"}:
            raise ValueError("invalid OpenAI-compatible capabilities")
        url = urlsplit(settings.openai_base_url)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("invalid provider endpoint")
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("remote providers require HTTPS")
        if url.scheme == "https" and settings.openai_api_key in {"", "EMPTY", "OPERATOR_REQUIRED"}:
            raise ValueError("remote endpoint credential must be supplied through environment")
    elif settings.provider == "anthropic" and not settings.anthropic_api_key:
        raise ValueError("Anthropic credential must be supplied through environment")


def validate_policy(policy) -> None:
    from .config import settings
    from .conversations.policy import Policy as DialoguePolicy

    billing = os.environ.get("LLM_BILLING_MODE")
    if not 0 <= settings.controls_inference_window_seconds <= 7200:
        raise ValueError("invalid inference window seconds")
    if settings.controls_inference_total_microunits is not None and not (
        0 <= settings.controls_inference_total_microunits <= 10**15
    ):
        raise ValueError("invalid inference total budget")
    if billing not in {"metered", "unmetered"}:
        raise ValueError("explicit LLM_BILLING_MODE required")
    if settings.provider == "local_stub" and billing != "unmetered":
        raise ValueError("local stub requires explicit unmetered billing")
    if billing == "metered" and (policy.input_price <= 0 or policy.output_price <= 0):
        raise ValueError("metered providers require positive conservative policy prices")
    if any(
        any(getattr(limit, unit) is None for unit in ("tokens", "microunits", "runs", "wall_ms"))
        for limit in policy.limits()
    ):
        raise ValueError("finite budget limits required at every scope")
    if not settings.controls_deployment_id or len(settings.controls_deployment_id) > 128:
        raise ValueError("stable deployment ID required")
    if DialoguePolicy.from_settings(settings).configuration_errors():
        raise ValueError(
            "explicit dialogue retention/cleanup policy required, also when saving is off"
        )


def prepare(directory: Path, policy_path: Path, api_port: int, frontend_port: int) -> dict:
    # New directory only; never adopt/reset an existing installation or policy.
    if directory.exists():
        raise ValueError(
            "prepare requires a new directory; use explicit migrate for an installation"
        )
    if api_port == frontend_port or not all(
        0 < port <= 65535 for port in (api_port, frontend_port)
    ):
        raise ValueError("two distinct fixed loopback ports required")
    deployment = os.environ.get("CONTROLS_DEPLOYMENT_ID", "")
    nonce = uuid.uuid4().hex
    manifest = {
        "schema": 1,
        "nonce": nonce,
        "deployment": deployment,
        "api_port": api_port,
        "frontend_port": frontend_port,
        "frontend_origin": f"http://127.0.0.1:{frontend_port}",
        "issuer": f"http://127.0.0.1:{frontend_port}/runtime/{nonce}",
    }
    environment(directory, manifest)
    from .controls.contracts import Policy

    policy = Policy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    validate_provider()
    validate_policy(policy)
    from .core.registry import get_active_pack

    versions = {
        exercise["id"]: os.environ.get("LOCAL_EXERCISE_VERSION", "local-v1")
        for module in get_active_pack().curriculum()
        for exercise in module["exercises"]
    }
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    host = RuntimeHost(f"http://127.0.0.1:{api_port}")
    private_write(
        directory / "identity-private.pem",
        host.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    private_write(
        directory / "public-key.pem",
        host.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ),
    )
    private_write(directory / "execution.key", Fernet.generate_key())
    private_write(
        directory / "authorization.json",
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
        ).encode(),
    )
    from .controls.ledger import Ledger
    from .conversations.ledger import DeletionLedger
    from .conversations.migration import migrate as migrate_dialogue
    from .store.db import engine

    DeletionLedger(str(directory / "deletions.jsonl")).initialize()
    migrate_dialogue(engine)
    Ledger(engine).initialize(policy)
    private_write(directory / "runtime.json", json.dumps(manifest, indent=2).encode())
    return {"prepared": True, "model_calls": 0, "listeners_started": False}


def load(directory: Path) -> dict:
    manifest = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("invalid runtime manifest")
    if (
        manifest["schema"] != 1
        or not manifest["nonce"]
        or not (directory / "belay.sqlite3").is_file()
    ):
        raise ValueError("installation requires explicit prepare/migrate")
    environment(directory, manifest)
    return manifest


def check(directory: Path) -> dict:
    manifest = load(directory)
    validate_provider()
    from sqlalchemy import func, inspect, select

    from .config import settings
    from .controls.admission import jobs
    from .controls.data import ExecutionData
    from .controls.ledger import Ledger, metadata
    from .conversations.ledger import DeletionLedger
    from .conversations.models import DialogueBase, SchemaVersion
    from .store.db import engine
    from .store.models import Base

    inspector = inspect(engine)
    for group in (Base.metadata, DialogueBase.metadata, metadata):
        for table in group.sorted_tables:
            if not inspector.has_table(table.name) or not {c.name for c in table.columns}.issubset(
                {c["name"] for c in inspector.get_columns(table.name)}
            ):
                raise ValueError("schema requires explicit migration")
    with engine.connect() as conn:
        if (
            conn.execute(
                select(SchemaVersion.version).where(SchemaVersion.name == "dialogue")
            ).scalar_one()
            != 1
        ):
            raise ValueError("unsupported dialogue schema")
        policy = Ledger(engine).policy(conn)
        job_counts = {
            str(state): cast(int, count)
            for state, count in conn.execute(
                select(jobs.c.state, func.count()).group_by(jobs.c.state)
            )
        }
    validate_policy(policy)
    if (
        manifest.get("pending_authorization", {}).get("policy_version", policy.version)
        != policy.version
    ):
        raise ValueError("pending authorization policy mismatch")
    DeletionLedger(settings.dialogue_deletion_ledger_file).deleted()
    ExecutionData(
        Ledger(engine), manifest["deployment"], (directory / "execution.key").read_bytes().strip()
    )
    host = runtime_host(directory, manifest)
    if host.key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ) != serialization.load_pem_public_key(
        (directory / "public-key.pem").read_bytes()
    ).public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo):
        raise ValueError("identity key mismatch")
    auth = json.loads((directory / "authorization.json").read_text())
    if not isinstance(auth.get("subjects"), dict) or not isinstance(
        auth.get("exercise_versions"), dict
    ):
        raise ValueError("invalid authorization configuration")
    blockers = []
    if (
        settings.controls_inference_expires_at
        and time.time() >= settings.controls_inference_expires_at
    ):
        blockers.append("inference_window_expired")
    if manifest.get("pending_authorization") and any(
        job_counts.get(state, 0) for state in ("queued", "running", "cancel_requested")
    ):
        blockers.append("pending_authorization_has_active_work")
    return {
        "checked": True,
        "provider": settings.provider,
        "models": settings.model_tiers if settings.provider != "local_stub" else None,
        "api": host.backend_origin,
        "frontend": host.origin + "/dev-client.html",
        "policy_version": policy.version,
        "price_version": policy.price_version,
        "period_seconds": policy.period_seconds,
        "model_quotas": policy.model_quotas.model_dump() if policy.model_quotas else None,
        "dialogue_saving": settings.dialogue_enabled,
        "inference_probe": False,
        "schema_initialized_at_start": False,
        "jobs_by_state": job_counts,
        "queued_work_may_execute": bool(job_counts.get("queued", 0)),
        "unknown_work_replayed": False,
        "start_allowed": not blockers,
        "blockers": blockers,
        "inference_total_microunits": settings.controls_inference_total_microunits,
        "inference_window": (
            {"state": "disabled", "mode": "amount_only"}
            if "amount_only_budget" in manifest
            else manifest.get("inference_window")
            or {"state": "unarmed", "seconds": settings.controls_inference_window_seconds}
        ),
    }


def runtime_host(directory: Path, manifest: dict) -> RuntimeHost:
    host = RuntimeHost(f"http://127.0.0.1:{manifest['api_port']}")
    host.origin, host.issuer = manifest["frontend_origin"], manifest["issuer"]
    key = serialization.load_pem_private_key(
        (directory / "identity-private.pem").read_bytes(), password=None
    )
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("RSA identity key required")
    host.key = key
    return host


def migrate(directory: Path, policy_path: Path) -> dict:
    load(directory)  # Missing DB, key or deletion fences are never regenerated.
    from sqlalchemy import inspect

    from .controls.contracts import Policy
    from .controls.ledger import Ledger
    from .conversations.ledger import DeletionLedger
    from .conversations.migration import migrate as migrate_dialogue
    from .store.db import engine

    policy = Policy.model_validate_json(policy_path.read_text(encoding="utf-8"))
    validate_policy(policy)
    DeletionLedger(str(directory / "deletions.jsonl")).deleted()
    Fernet((directory / "execution.key").read_bytes().strip())
    migrate_dialogue(engine)
    ledger = Ledger(engine)
    if inspect(engine).has_table("control_jobs"):
        ledger.upgrade_schema()
    ledger.initialize(policy)  # Different installed policy is rejected, never reset.
    return {"migrated": True, "model_calls": 0}


def use_amount_only_budget(directory: Path) -> dict:
    """Explicit stopped-host transition. No policy/ledger writes or new allowance."""
    load(directory)
    from sqlalchemy import select

    from .config import settings
    from .controls.admission import jobs
    from .store.db import engine

    with lock_directory(directory):
        manifest = load(directory)
        receipt_path = directory / "running.json"
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt.get("nonce") != manifest["nonce"]:
                raise ValueError("runtime receipt mismatch")
            # The managed host owns this lock for its entire lifetime. Holding
            # it here plus free ports proves a matching receipt is stale; keep
            # that evidence intact rather than deleting it to permit an update.
        check_loopback_port(manifest["api_port"])
        check_loopback_port(manifest["frontend_port"])
        if manifest.get("pending_authorization"):
            raise ValueError("pending authorization requires review")
        with engine.connect() as conn:
            if conn.execute(
                select(jobs.c.id).where(jobs.c.state.in_(["queued", "running", "cancel_requested"]))
            ).first():
                raise ValueError("inspect existing active/queued work first")
        if "amount_only_budget" in manifest:
            return {
                "mode": "amount_only",
                "unchanged": True,
                "inference_total_microunits": amount_only_cap(manifest),
                "model_calls": 0,
            }
        old_window = manifest.get("inference_window")
        # Existing timed authorizations must carry their own ceiling. Never take
        # a larger env value when removing an existing authorization's deadline.
        cap = (
            old_window.get("total_microunits")
            if old_window is not None
            else settings.controls_inference_total_microunits
        )
        updated = {**manifest, "amount_only_budget": {"total_microunits": cap}}
        updated.pop("inference_window", None)
        amount_only_cap(updated)
        # Preflight schema, identity and installed prices; expiry alone is the
        # blocker this operator action is authorized to remove.
        preflight = check(directory)
        if any(code != "inference_window_expired" for code in preflight["blockers"]):
            raise ValueError("budget mode transition blocked")
        updated["budget_mode_history"] = [
            *manifest.get("budget_mode_history", []),
            {
                "mode": "amount_only",
                "changed_at": time.time(),
                "total_microunits": cap,
                "additional_microunits": 0,
                "previous_window": old_window,
            },
        ]
        temporary = directory / ("budget-mode-" + uuid.uuid4().hex + ".pending")
        try:
            private_write(temporary, json.dumps(updated, indent=2).encode())
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, directory / "runtime.json")
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "mode": "amount_only",
            "unchanged": False,
            "inference_total_microunits": cap,
            "additional_microunits": 0,
            "database_changed": False,
            "stale_receipt_retained": receipt_path.exists(),
            "model_calls": 0,
            "listeners_started": False,
        }


def authorize_budget(directory: Path, policy_path: Path, authorization_path: Path) -> dict:
    """Explicit finite amount-only grant; policy then manifest, retryable by ID.

    If manifest replacement fails, the old cumulative ceiling remains enforced.
    No retry calculates a new ceiling from consumed usage or adds money twice.
    """
    import hashlib

    load(directory)
    from sqlalchemy import select

    from .controls.admission import jobs
    from .controls.contracts import Policy
    from .controls.ledger import Ledger
    from .store.db import engine

    auth = json.loads(authorization_path.read_text())
    policy = Policy.model_validate_json(policy_path.read_text())
    amount, old_cap = auth["additional_microunits"], auth["expected_total_microunits"]
    identifier = auth["id"]
    if (
        type(amount) is not int
        or type(old_cap) is not int
        or not 0 < amount <= 10**15
        or not 0 <= old_cap <= 10**15 - amount
        or not isinstance(identifier, str)
        or not 1 <= len(identifier) <= 64
        or auth["unused_balance"] != "retain"
    ):
        raise ValueError("invalid explicit budget grant")
    ceiling = old_cap + amount
    proof = hashlib.sha256(
        json.dumps({"authorization": auth, "policy": policy.model_dump()}, sort_keys=True).encode()
    ).hexdigest()
    with lock_directory(directory):
        manifest = load(directory)
        if "amount_only_budget" not in manifest:
            raise ValueError("amount-only mode required")
        if auth["expected_deployment_id"] != manifest["deployment"]:
            raise ValueError("budget grant deployment mismatch")
        receipt = directory / "running.json"
        if receipt.exists() and json.loads(receipt.read_text()).get("nonce") != manifest["nonce"]:
            raise ValueError("runtime receipt mismatch")
        check_loopback_port(manifest["api_port"])
        check_loopback_port(manifest["frontend_port"])
        previous = next(
            (r for r in manifest.get("budget_grant_history", []) if r["id"] == identifier), None
        )
        if previous:
            if previous["proof"] != proof:
                raise ValueError("budget grant ID conflict")
            return {
                "authorized": True,
                "unchanged": True,
                "authorization_id": identifier,
                "model_calls": 0,
            }
        if amount_only_cap(manifest) != old_cap:
            raise ValueError("cumulative ceiling changed; review authorization")
        validate_policy(policy)
        if any(limit.microunits != ceiling for limit in policy.limits()):
            raise ValueError("scope ceilings must match approved local grant")
        ledger = Ledger(engine)
        with engine.connect() as conn:
            installed = ledger.policy(conn)
            if conn.execute(
                select(jobs.c.id).where(jobs.c.state.in_(["queued", "running", "cancel_requested"]))
            ).first():
                raise ValueError("inspect existing active/queued work first")
        if installed != policy:
            if installed.version != auth["expected_policy_version"]:
                raise ValueError("installed policy changed")
            old, new = installed.model_dump(), policy.model_dump()
            for key in (
                "version",
                "deployment",
                "institution",
                "classroom",
                "learner",
                "model_quotas",
            ):
                old.pop(key)
                new.pop(key)
            if old != new:
                raise ValueError("budget grant cannot change prices, period or traffic")
            ledger.update_policy(policy)
        # Same target policy is accepted after a DB-commit/file-write fault.
        # The new cap is pinned to the approved OLD cap, not a fresh balance.
        manifest["amount_only_budget"] = {"total_microunits": ceiling}
        manifest["budget_grant_history"] = [
            *manifest.get("budget_grant_history", []),
            {
                "id": identifier,
                "proof": proof,
                "changed_at": time.time(),
                "old_total_microunits": old_cap,
                "total_microunits": ceiling,
                "additional_microunits": amount,
                "unused_balance": "retain",
                "policy_version": policy.version,
            },
        ]
        temporary = directory / ("budget-grant-" + uuid.uuid4().hex + ".pending")
        try:
            private_write(temporary, json.dumps(manifest, indent=2).encode())
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, directory / "runtime.json")
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "authorized": True,
            "unchanged": False,
            "authorization_id": identifier,
            "total_microunits": ceiling,
            "additional_microunits": amount,
            "model_calls": 0,
            "listeners_started": False,
        }


def authorize_window(directory: Path, policy_path: Path, authorization_path: Path) -> dict:
    """Explicit local operator authorization; stopped host, never implicit renewal.

    Reuse Ledger.update_policy. If the process fails after the DB commit, the old
    expired manifest still fences execution; retry the identical authorization.
    """
    import hashlib

    manifest = load(directory)
    from sqlalchemy import select

    from .controls.admission import jobs
    from .controls.contracts import Policy
    from .controls.ledger import Ledger, attempts
    from .store.db import engine

    authorization = json.loads(authorization_path.read_text())
    proof = hashlib.sha256(json.dumps(authorization, sort_keys=True).encode()).hexdigest()
    identifier = authorization["id"]
    amount, seconds = authorization["additional_microunits"], authorization["seconds"]
    if (
        not isinstance(identifier, str)
        or not 1 <= len(identifier) <= 64
        or type(amount) is not int
        or not 0 < amount <= 10**15
        or type(seconds) is not int
        or not 0 < seconds <= 7200
        or authorization["unused_balance"] != "forfeit"
    ):
        raise ValueError("invalid explicit authorization")
    policy = Policy.model_validate_json(policy_path.read_text())
    with lock_directory(directory):
        manifest = load(directory)
        previous = next(
            (a for a in manifest.get("authorization_history", []) if a["id"] == identifier), None
        )
        if previous:
            if previous["proof"] != proof or previous["policy_version"] != policy.version:
                raise ValueError("authorization ID conflict")
            return {"authorized": True, "unchanged": True, "authorization_id": identifier}
        if (directory / "running.json").exists():
            raise ValueError("stop the matching installation first")
        check_loopback_port(manifest["api_port"])
        check_loopback_port(manifest["frontend_port"])
        old_window = manifest.get("inference_window")
        if (
            not old_window
            or old_window["expires"] > time.time()
            or manifest.get("pending_authorization")
        ):
            raise ValueError("only an expired authorization can be replaced")
        ledger = Ledger(engine)
        with ledger.transaction() as conn:
            installed = ledger.policy(conn)
            if conn.execute(
                select(jobs.c.id).where(jobs.c.state.in_(["queued", "running", "cancel_requested"]))
            ).first():
                raise ValueError("inspect existing active/queued work first")
            rows = list(conn.execute(select(attempts)).mappings())
            # A loopback installation owns one deployment; never count another ledger.
            deployment_key = hashlib.sha256(
                json.dumps([manifest["deployment"]]).encode()
            ).hexdigest()
            if any(row["scopes"][0] != deployment_key for row in rows):
                raise ValueError("mixed deployment ledger requires separate review")
            consumed = sum(row["actual"]["microunits"] for row in rows if row["actual"] is not None)
            held = sum(row["reserved"]["microunits"] for row in rows if row["actual"] is None)
        if consumed != authorization["expected_consumed_microunits"]:
            raise ValueError("ledger changed; authorization needs review")
        ceiling = consumed + amount
        # Holds are NOT refunded or added to the grant; they continue to encumber it.
        if held > amount or any(limit.microunits != ceiling for limit in policy.limits()):
            raise ValueError("policy does not match approved incremental amount")
        validate_policy(policy)
        if installed != policy:
            if installed.version != authorization["expected_policy_version"]:
                raise ValueError("installed policy changed")
            old, new = installed.model_dump(), policy.model_dump()
            old.pop("version")
            new.pop("version")
            for level in ("deployment", "institution", "classroom", "learner"):
                old[level].pop("microunits")
                new[level].pop("microunits")
            if old != new:
                raise ValueError("window authorization only changes currency allowance")
            ledger.update_policy(policy)
        pending = {
            "id": identifier,
            "seconds": seconds,
            "total_microunits": ceiling,
            "policy_version": policy.version,
        }
        entry = {
            **pending,
            "proof": proof,
            "additional_microunits": amount,
            "consumed_microunits": consumed,
            "held_microunits": held,
            "unused_balance": "forfeit",
            "previous_window": old_window,
        }
        manifest.pop("inference_window")
        manifest["pending_authorization"] = pending
        manifest["authorization_history"] = [*manifest.get("authorization_history", []), entry]
        temporary = directory / ("authorization-" + uuid.uuid4().hex + ".pending")
        try:
            private_write(temporary, json.dumps(manifest, indent=2).encode())
            with temporary.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, directory / "runtime.json")
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "authorized": True,
            "authorization_id": identifier,
            "starts": "first_manual_start",
            "seconds": seconds,
            "additional_microunits": amount,
            "total_microunits": ceiling,
            "held_microunits": held,
            "model_calls": 0,
        }


def start(directory: Path) -> dict:
    load(directory)  # A missing installation must not even create a lock directory.
    try:
        installation_lock = lock_directory(directory)
    except OSError:
        raise RuntimeError("runtime_already_running_or_locked") from None
    with installation_lock:
        status = check(directory)
        if status.get("blockers"):
            raise RuntimeError(status["blockers"][0])
        manifest = load(directory)
        if manifest.get("pending_authorization"):
            from sqlalchemy import select

            from .controls.admission import jobs
            from .controls.ledger import Ledger
            from .store.db import engine

            with Ledger(engine).transaction() as conn:
                if conn.execute(
                    select(jobs.c.id).where(
                        jobs.c.state.in_(["queued", "running", "cancel_requested"])
                    )
                ).first():
                    raise ValueError("review old work before first authorized start")
        host = runtime_host(directory, manifest)
        check_loopback_port(manifest["api_port"])
        check_loopback_port(manifest["frontend_port"])
        manifest = arm_inference_window(directory, manifest)
        status = {
            **status,
            "inference_window": manifest.get("inference_window", status.get("inference_window")),
        }
        from .controls.jobs_worker import start_worker

        # Explicit preflight passed: imports/constructors must not perform DDL.
        from .main import app

        api_socket = socket.socket()
        frontend = None
        worker_stop = worker_thread = front_thread = monitor = None
        stop_monitor = threading.Event()
        receipt = directory / "running.json"
        signal_file = directory / "stop.request"
        try:
            api_socket.bind(("127.0.0.1", manifest["api_port"]))
            api_socket.listen(128)
            frontend = ThreadingHTTPServer(
                ("127.0.0.1", manifest["frontend_port"]), host.handler(ROOT / "frontend")
            )
            server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning"))
            signal_file.unlink(missing_ok=True)  # Stale stop signal, never a task pointer.
            worker_stop, worker_thread = start_worker()
            front_thread = threading.Thread(target=frontend.serve_forever, daemon=True)
            front_thread.start()

            def supervise():
                ready = False
                while not stop_monitor.wait(0.2):
                    if signal_file.exists() or not worker_thread.is_alive():
                        worker_stop.set()
                        server.should_exit = True
                        break
                    if not ready and server.started:
                        ready = True
                        print(
                            json.dumps(
                                {
                                    "ready": True,
                                    "api": host.backend_origin,
                                    "frontend": host.origin + "/dev-client.html",
                                    "worker_alive": True,
                                }
                            ),
                            flush=True,
                        )

            monitor = threading.Thread(target=supervise, daemon=True)
            monitor.start()
            receipt.write_text(
                json.dumps(
                    {
                        **status,
                        "pid": os.getpid(),
                        "nonce": manifest["nonce"],
                        "worker": worker_thread.name,
                        "worker_alive": worker_thread.is_alive(),
                    }
                ),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        **status,
                        "worker": worker_thread.name,
                        "stop": "Ctrl+C or controlled_runtime stop",
                    }
                ),
                flush=True,
            )
            server.run(sockets=[api_socket])
        finally:
            stop_monitor.set()
            if worker_stop is not None:
                worker_stop.set()
            # Join an in-flight bounded call; never refund or erase unknown work.
            if worker_thread is not None:
                worker_thread.join()
            if front_thread is not None:
                assert frontend is not None
                frontend.shutdown()
                front_thread.join(timeout=5)
            if frontend is not None:
                frontend.server_close()
            if monitor is not None:
                monitor.join(timeout=5)
            api_socket.close()
            receipt.unlink(missing_ok=True)
            signal_file.unlink(missing_ok=True)
        return {"stopped": True}


def stop(directory: Path) -> dict:
    manifest = json.loads((directory / "runtime.json").read_text())
    receipt = json.loads((directory / "running.json").read_text())
    if receipt["nonce"] != manifest["nonce"]:
        raise ValueError("runtime receipt mismatch")
    if not (directory / "launcher.lock").is_file():
        raise RuntimeError("runtime_not_running")
    try:
        with lock_directory(directory):
            pass
    except OSError:
        pass  # The installation lock is held by its foreground host.
    else:
        raise RuntimeError("runtime_not_running")
    # Cooperative signal only: never kill a process identified just by PID/port.
    (directory / "stop.request").touch()
    return {"stop_requested": True, "stopped": False}


def load_environment(env_file: Path | None, credentials_file: Path | None) -> None:
    """Process credentials win; supplemental file supplies credentials only."""
    credentials = {"OPENAI_API_KEY", "LLM_API_KEY", "ANTHROPIC_API_KEY"}
    inherited = {key for key in credentials if os.environ.get(key)}
    for path, credentials_only in ((env_file, False), (credentials_file, True)):
        if path is None:
            continue
        if not path.is_file():
            raise ValueError("environment file missing")
        for key, value in dotenv_values(path).items():
            if value is None or (credentials_only and key not in credentials):
                continue
            if key in credentials and key in inherited:
                continue
            if credentials_only and os.environ.get(key):
                continue
            os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "prepare",
            "migrate",
            "check",
            "start",
            "stop",
            "authorize-window",
            "authorize-budget",
            "use-amount-only-budget",
        ],
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--credentials-env-file", type=Path)
    parser.add_argument("--prompt-missing-key", action="store_true")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--api-port", type=int, default=8004)
    parser.add_argument("--frontend-port", type=int, default=5177)
    args = parser.parse_args(argv)
    try:
        load_environment(args.env_file, args.credentials_env_file)
        if args.command == "start" and args.prompt_missing_key:
            provider = os.environ.get("PROVIDER", "openai_compatible")
            names = {
                "openai_compatible": ("OPENAI_API_KEY", "LLM_API_KEY"),
                "anthropic": ("ANTHROPIC_API_KEY",),
            }.get(provider, ())
            if names and not any(os.environ.get(key) for key in names):
                if not sys.stdin.isatty():
                    raise ValueError("missing credential requires an interactive terminal")
                os.environ[names[0]] = getpass.getpass(
                    "Provider API key (missing from configuration): "
                )
        directory = args.data_dir.resolve()
        if args.command in {"prepare", "migrate"} and not args.policy:
            raise ValueError("explicit policy required")
        if args.command == "prepare":
            result = prepare(directory, args.policy, args.api_port, args.frontend_port)
        elif args.command == "migrate":
            load(directory)
            with lock_directory(directory):
                result = migrate(directory, args.policy)
        elif args.command in {"authorize-window", "authorize-budget"}:
            if not args.policy or not args.authorization:
                raise ValueError("explicit policy and authorization required")
            grant = authorize_window if args.command == "authorize-window" else authorize_budget
            result = grant(directory, args.policy, args.authorization)
        elif args.command == "use-amount-only-budget":
            result = use_amount_only_budget(directory)
        else:
            result = {"check": check, "start": start, "stop": stop}[args.command](directory)
        print(json.dumps(result))
        return 1 if args.command == "check" and not result.get("start_allowed", True) else 0
    except Exception as exc:
        # No connection strings, credentials, raw SDK errors or learner data.
        safe_codes = {
            "inference_window_expired": "inference_window_expired",
            "inference authorization expired; explicit review required": "inference_window_expired",
            "local port already has a listener": "port_in_use",
            "runtime_not_running": "runtime_not_running",
            "runtime_already_running_or_locked": "runtime_already_running_or_locked",
            "pending_authorization_has_active_work": "pending_authorization_has_active_work",
            "runtime receipt mismatch": "runtime_receipt_mismatch",
            "environment file missing": "environment_file_missing",
            "stop the matching installation first": "stop_installation_first",
            "pending authorization requires review": "pending_authorization_requires_review",
            "inspect existing active/queued work first": "active_work_requires_review",
            "invalid amount-only budget": "finite_persisted_budget_required",
        }
        code = safe_codes.get(str(exc), "controlled_runtime_unavailable")
        if isinstance(exc, FileNotFoundError):
            code = "required_file_missing"
        print(json.dumps({"error": code, "action": args.command}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
