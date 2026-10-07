# SPDX-License-Identifier: AGPL-3.0-only
"""The same authenticated dialogue API for the legacy and standalone Quad edges."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from ..agent import run_turn
from ..agent.distress import extra_terms, has_distress_signal
from ..auth import _bearer, authorize, denied
from ..config import settings
from ..integrations.quad.pii import PIIRejected, assert_no_pii
from ..store.scoped import scoped_store
from .bounds import BoundedProvider, bounded_route, recent_window
from .policy import Policy
from .repository import ConversationStore, digest

PLACEHOLDER = "[This exchange was not saved.]"


class CreateAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    exercise_id: str = Field(max_length=64)
    exercise_version: str = Field(max_length=64)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    save: StrictBool = False


class NewTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    expected_revision: int = Field(ge=0)
    message: str = Field(min_length=1)
    source: str = ""
    mode: Literal["study", "teach"] = "study"
    stance: Literal["peer", "oracle", "control"] = "peer"
    result: dict | None = None
    overlay: dict | None = None


def pii_content(text: str) -> bool:
    try:
        assert_no_pii({"text": text})
    except PIIRejected:
        return True
    return False


def private_content(text: str) -> bool:
    return pii_content(text) or has_distress_signal(text, extra_terms(settings))


def build_router(
    prefix, consent_router, pack, llm_factory, *, engine=None, policy=None, tutor=run_turn
):
    if engine is None:
        from ..store.db import engine as default_engine

        engine = default_engine

    def store():
        return ConversationStore(engine, policy or Policy.from_settings(settings))

    api = APIRouter(
        prefix=prefix + "/conversations",
        dependencies=[Depends(authorize)],
        route_class=bounded_route(lambda: store().policy),
    )

    @api.get("/config")
    def configuration(request: Request):
        p = store().policy
        if p.enabled:
            store()._ready()
        return {
            "enabled": p.enabled,
            "optional": True,
            "policy_id": p.policy_id,
            "retention_seconds": p.retention_seconds if p.enabled else 0,
            "retention_clock": "creation",
            "research_consent_required": False,
            "identity": {
                "institution_id": request.state.identity.institution_id,
                "class_id": request.state.identity.class_id,
                "learner_id": request.state.identity.learner_id,
            },
            "assignments": dict(request.state.identity.active_assignments),
        }

    @api.post("")
    def create(request: Request, body: CreateAttempt):
        if not body.save:
            return {"saved": False, "conversation_id": None}
        return {"saved": True, **store().create(request.state.identity, body.request_id)}

    @api.get("")
    def attempts(request: Request, exercise_id: str, exercise_version: str):
        return {"attempts": store().attempts(request.state.identity, exercise_id, exercise_version)}

    @api.get("/{cid}")
    def metadata(request: Request, cid: str):
        return store().get(request.state.identity, cid)

    @api.get("/{cid}/messages")
    def history(request: Request, cid: str, before: str | None = None):
        return store().history(request.state.identity, cid, before)

    @api.delete("/{cid}", status_code=204)
    def remove(request: Request, cid: str):
        store().delete(request.state.identity, cid)
        return Response(status_code=204)

    @api.post("/{cid}/turns")
    async def turn(request: Request, cid: str, body: NewTurn):
        repository = store()
        identity = request.state.identity
        meta = repository.get(identity, cid)
        identity = replace(
            identity, exercise_id=meta["exercise_id"], exercise_version=meta["exercise_version"]
        )
        try:
            exercise = pack.get_exercise(identity.exercise_id)
        except KeyError:
            raise denied() from None
        if len(body.message.encode()) > repository.policy.max_message_bytes:
            raise HTTPException(413, "message limit exceeded")
        screened = private_content(body.message) or private_content(body.source)
        replay = repository.begin(
            identity,
            cid,
            body.request_id,
            digest(body.model_dump(exclude={"expected_revision"})),
            body.expected_revision,
            PLACEHOLDER if screened else body.message,
        )
        if replay is not None:
            return replay
        try:
            recent = recent_window(
                repository.context(identity, cid), body.message, pack.persona.id, repository.policy
            )
            payload = {
                "participant_id": identity.learner_id,
                "exercise": exercise,
                "event": "chat",
                "mode": body.mode,
                "stance": body.stance,
                "source": body.source,
                "result": body.result,
                "overlay": body.overlay,
                "recent": recent,
            }
            provider = llm_factory()
            bounded = BoundedProvider(provider, repository.policy) if provider is not None else None
            released = await run_in_threadpool(
                tutor, payload, bounded, scoped_store(consent_router, identity)
            )
            # Only the final learner-facing response released by the existing gate.
            message = str(released["message"])
            question = released.get("check_question")
            if question is not None and not isinstance(question, str):
                raise ValueError("invalid released response")
            live_message, live_question = message, question
            unsafe_output = pii_content(message + (question or ""))
            if screened or private_content(message + (question or "")):
                message, question = PLACEHOLDER, None
            # Re-read credentials and current membership after the model call.
            fresh = await authorize(request, await _bearer(request))
            result = repository.complete(
                fresh, cid, body.request_id, {"message": message, "check_question": question}
            )
            if screened and not unsafe_output:
                # Preserve the live support response without storing its content.
                result = {
                    **result,
                    "unsaved_exchange": True,
                    "response": {"message": live_message, "check_question": live_question},
                }
            return result
        except HTTPException:
            repository.fail(identity, cid, body.request_id)
            raise
        except Exception:
            repository.fail(identity, cid, body.request_id)
            raise HTTPException(502, "tutor unavailable") from None

    return api
