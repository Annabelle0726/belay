# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated unsaved Ask admission and recovery over the existing coordinator."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, select

from ..auth import authorize, denied
from ..config import settings
from ..schemas import SolTurnRequest
from .admission import jobs
from .contracts import ControlError
from .data import ExecutionData
from .http import control_http_error
from .ledger import Ledger


@lru_cache(maxsize=4)
def _configured_store(url: str, deployment: str, key: bytes) -> ExecutionData:
    # No schema creation or fallback to the application/research database.
    return ExecutionData(Ledger(create_engine(url, pool_pre_ping=True)), deployment, key)


def execution_store() -> ExecutionData:
    if not settings.controls_jobs_enabled:
        raise ControlError("jobs_disabled", 503)
    if settings.controls_mode != "enforced":
        raise ControlError("invalid_controls_mode", 503)
    if not all(
        (
            settings.controls_database_url,
            settings.controls_deployment_id,
            settings.controls_data_key_file,
        )
    ):
        raise ControlError("jobs_not_configured", 503)
    try:
        key = Path(settings.controls_data_key_file).read_bytes().strip()
        return _configured_store(
            settings.controls_database_url, settings.controls_deployment_id, key
        )
    except (OSError, ValueError, TypeError):
        raise ControlError("jobs_not_configured", 503) from None


class BoundedJobRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request):
            # Bound bytes before FastAPI/auth JSON parsing. Never log the body.
            if request.method == "POST":
                size, parts = 0, []
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 1048576:
                        raise HTTPException(413, {"code": "payload_too_large"})
                    parts.append(chunk)
                request._body = b"".join(parts)
            try:
                response = await original(request)
            except ControlError as exc:
                raise control_http_error(exc) from exc
            except HTTPException as exc:
                exc.headers = {
                    **(exc.headers or {}),
                    "Cache-Control": "no-store",
                    "Vary": "Authorization, X-Belay-Institution, X-Belay-Class",
                }
                raise
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization, X-Belay-Institution, X-Belay-Class"
            return response

        return handle


class AskSubmission(SolTurnRequest):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    exercise_version: str = Field(min_length=1, max_length=64)


class RecoveryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$")
    exercise_id: str = Field(min_length=1, max_length=128)
    exercise_version: str = Field(min_length=1, max_length=64)


def build_jobs_router(prefix: str, pack) -> APIRouter:
    api = APIRouter(prefix=prefix, dependencies=[Depends(authorize)], route_class=BoundedJobRoute)

    @api.get("/config")
    def config(request: Request):
        store = execution_store()
        identity = request.state.identity
        with store.ledger.transaction() as conn:
            policy = store.ledger.policy(conn)
            continuations = []
            try:
                approval = json.loads(settings.controls_operator_continuations or "{}")
            except (ValueError, TypeError):
                approval = {}
            candidates = approval.get("request_ids", []) if isinstance(approval, dict) else []
            if (
                isinstance(approval, dict)
                and approval.get("policy_version") == policy.version
                and isinstance(candidates, list)
                and len(candidates) <= 32
                and all(cap.active_jobs >= 2 and cap.model_calls >= 2 for cap in policy.traffic())
            ):
                for request_id in candidates:
                    if not isinstance(request_id, str) or not re.fullmatch(
                        r"[A-Za-z0-9_-]{16,128}", request_id
                    ):
                        continue
                    job_id = store.job_id(identity, request_id)
                    state = conn.execute(
                        select(jobs.c.state).where(jobs.c.id == job_id)
                    ).scalar_one_or_none()
                    if state != "unknown":
                        continue
                    try:
                        store._owned(conn, job_id, identity)
                    except (ControlError, HTTPException):
                        continue
                    continuations.append(request_id)
        return {
            "operator_continuations": continuations,
            "missing_request_recovery": 1,
            "reply_references": {"version": 1, "passages": False},
            "recovery_scope": identity.grant_ref,
            "learner_id": identity.learner_id,
            "assignments": dict(identity.active_assignments),
            "poll_seconds": policy.poll_seconds,
            "result_seconds": policy.result_seconds,
            "notice": "Unsaved Ask temporarily stores encrypted input and results for recovery. Input expires after the queue/execution limit; results expire after the stated retention. This does not save conversation history.",
        }

    @api.post("", status_code=202)
    def submit(request: Request, body: AskSubmission):
        identity = request.state.identity
        try:
            pack.get_exercise(identity.exercise_id)
        except KeyError:
            raise denied() from None
        payload = body.model_dump(exclude={"request_id", "exercise_version"})
        return execution_store().submit(identity, body.request_id, payload, prefix)

    @api.get("/by-request/{request_id}")
    def by_request(request: Request, request_id: str):
        store = execution_store()
        return store.status(
            request.state.identity, store.job_id(request.state.identity, request_id)
        )

    @api.post("/by-request/{request_id}/reconcile")
    def reconcile(request: Request, request_id: str, body: RecoveryContext):
        if request_id != body.request_id:
            raise HTTPException(422, {"code": "request_invalid"})
        return execution_store().reconcile_missing(request.state.identity, request_id)

    @api.get("/{job_id}")
    def status(request: Request, job_id: str):
        return execution_store().status(request.state.identity, job_id)

    return api
