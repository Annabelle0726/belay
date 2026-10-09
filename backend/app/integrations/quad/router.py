# SPDX-License-Identifier: AGPL-3.0-only
"""
Quad tutor-seam sidecar — a versioned /quad/v1 HTTP/JSON surface over the
framework's existing evaluation-first tutor loop.

Apache-2.0-compatible. Imports CORE ONLY (`app.agent`, `app.core`, `app.store`,
`app.config`) — never `packs.*`; the active pack is resolved through the core
registry. See ARCHITECTURE.md (HTTP surface / Quad sidecar) and VALIDATION.md.

Hard constraints (EduCloud privacy posture):
  - Identity is pseudonymous ONLY: a host numeric user id namespaced by provider,
    e.g. ``gh:12345``, which IS the participant anon-code namespace. PII (names,
    SIS ids, plaintext email) is refused at the boundary (`pii.assert_no_pii`).
  - GRADES FIREWALL: a ``gradingspec_result`` arrives ONLY as read-only context
    for the turn. There is NO write path from the sidecar to any grading surface;
    the tutor never writes grades.
  - The sidecar exposes the existing loop and adds NO prompt-level decision; the
    deterministic governance gate is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from ...agent import distress as _distress
from ...agent import get_llm, run_turn
from ...agent import goals as _goals
from ...agent import overlay as _overlay
from ...auth import authorize, denied
from ...config import settings
from ...core.registry import get_active_pack
from ...store import ConsentRouter, InMemoryStore, SqlStore
from ...store.scoped import register, scoped_store
from .pii import PIIRejected, assert_no_pii
from .schemas import QuadTurnRequest

PROTOCOL_VERSION = "quad/v1"


def build_router(
    consent_router: ConsentRouter, pack, llm_factory: Callable[[], object]
) -> APIRouter:
    """Build the /quad/v1 router over an injected wiring (testable without network).

    `llm_factory` is called lazily on the first non-control turn; control-stance
    turns never invoke it.
    """
    api = APIRouter(prefix="/quad/v1", tags=["quad"])
    _llm_cache: dict = {}

    def _llm():
        if "inst" not in _llm_cache:
            _llm_cache["inst"] = llm_factory()
        return _llm_cache["inst"]

    @api.get("/health")
    def health():
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "pack": pack.id,
            "provider": settings.provider,
        }

    @api.get("/capabilities")
    def capabilities():
        return {
            "protocol": PROTOCOL_VERSION,
            "framework": "peer-tutor-framework",
            "pack": pack.id,
            "provider": settings.provider,
            "identity": {
                "scheme": "pseudonymous",
                "format": "provider:numeric-id",
                "example": "gh:12345",
            },
            "authentication": {
                "scheme": "Bearer",
                "algorithm": "RS256",
                "authorization": "operator-owned institution/class/learner and assignment-version grants",
                "selectors": ["X-Belay-Institution", "X-Belay-Class"],
            },
            "grades": {
                "mode": "read-only",
                "writes": False,
                "gradingspec_result": "accepted as read-only turn context (gradingspec convergence)",
            },
            "instructor_surfaces": "class-level aggregates only",
            "privacy": "no names, SIS ids, or plaintext email; pseudonymous id only",
            "stances": ["peer", "oracle", "control"],
            "routes": [
                f"GET /{PROTOCOL_VERSION}/health",
                f"GET /{PROTOCOL_VERSION}/capabilities",
                f"POST /{PROTOCOL_VERSION}/turn",
                f"POST /{PROTOCOL_VERSION}/goals",
                f"POST /{PROTOCOL_VERSION}/reflection",
                f"POST /{PROTOCOL_VERSION}/overlay",
                f"POST /{PROTOCOL_VERSION}/events",
            ],
            "learner_goals": "opt-in; the student's own words, pseudonymous, never to grades",
            # Bounded, enumerated per-learner customization. Input, never authority:
            # it shapes HOW the tutor helps and can NEVER loosen the leak gate or the
            # wellbeing floor (no dial yields more of the answer).
            "customization": {
                "scheme": "bounded-enumerated-overlay",
                "fields": {
                    "persona": {
                        "tone": ["warm", "neutral", "direct"],
                        "verbosity": ["brief", "balanced", "detailed"],
                        "framing": ["peer", "coach"],
                    },
                    "pedagogy": {
                        "scaffolding": ["more", "default", "less"],
                        "stretch": ["low", "default", "high"],
                    },
                    "accommodation": {
                        "reading_level": ["plain", "default", "advanced"],
                        "language": "short locale token (e.g. en, es)",
                    },
                },
                "floors": "leak gate + wellbeing floor are supreme and NOT customizable",
            },
            "license": "Apache-2.0",
        }

    @api.post("/turn", dependencies=[Depends(authorize)])
    def turn(request: Request, payload: dict = Body(...)):
        # 1. PII boundary on the RAW body (before any parsing/storage).
        try:
            assert_no_pii(payload)
        except PIIRejected as e:
            raise HTTPException(422, f"PII rejected at boundary: {e}") from e
        # 2. Validate the turn shape.
        try:
            req = QuadTurnRequest(**{**payload, "pseudo_id": request.state.identity.learner_id})
        except ValidationError as e:
            raise HTTPException(422, f"invalid quad turn request: {e}") from e
        # 3. Resolve the exercise via the active pack (core registry).
        try:
            ex = pack.get_exercise(req.exercise_id)
        except KeyError:
            raise denied() from None

        # 4. Build the tutor-loop payload. gradingspec_result is READ-ONLY context
        #    mapped onto the turn's run-result slot — never written back anywhere.
        turn_payload = {
            "participant_id": req.pseudo_id,  # pseudonymous id only
            "exercise": ex,
            "event": req.event,
            "mode": req.mode,
            "stance": req.stance,
            "source": req.source,
            "result": req.gradingspec_result,
            "recent": [t.model_dump() for t in req.recent],
            "signals": req.signals,
            "request": payload.get("request"),  # e.g. "reflect" (student-initiated)
            # Optional per-learner customization overlay; floor-checked in run_turn.
            "overlay": req.overlay,
        }
        # 5. Consent and storage use the trusted class learner namespace.
        register(consent_router, request.state.identity, req.consent)
        store = scoped_store(consent_router, request.state.identity)
        try:
            return run_turn(turn_payload, _llm(), store)
        except HTTPException:
            raise
        except Exception as e:  # surface a clean error
            raise HTTPException(502, "tutor unavailable") from e

    @api.post("/goals", dependencies=[Depends(authorize)])
    def goals(request: Request, payload: dict = Body(...)):
        """Set/update/clear the student's own goals (opt-in). Same PII boundary as
        everything else; pseudonymous id only; never written to grades."""
        try:
            assert_no_pii(payload)
        except PIIRejected as e:
            raise HTTPException(422, f"PII rejected at boundary: {e}") from e
        pid = request.state.identity.learner_id
        if "consent" in payload and type(payload["consent"]) is not bool:
            raise HTTPException(422, "consent must be boolean")
        register(consent_router, request.state.identity, payload.get("consent", False))
        store = scoped_store(consent_router, request.state.identity)
        artifact = _goals.set_goals(store, pid, payload.get("text", ""))
        resp = {"ok": True, "pseudo_id": pid, "goals": artifact}
        if artifact and artifact.get("floor") == "distress":  # Slice G: surface the frame
            resp["distress_support"] = _distress.frame_from_settings(settings)
        return resp

    @api.post("/reflection", dependencies=[Depends(authorize)])
    def reflection(request: Request, payload: dict = Body(...)):
        """Record a student reflection (opt-in), linked to their current goal. Same
        PII boundary; pseudonymous id only; never written to grades."""
        try:
            assert_no_pii(payload)
        except PIIRejected as e:
            raise HTTPException(422, f"PII rejected at boundary: {e}") from e
        pid = request.state.identity.learner_id
        if "consent" in payload and type(payload["consent"]) is not bool:
            raise HTTPException(422, "consent must be boolean")
        register(consent_router, request.state.identity, payload.get("consent", False))
        store = scoped_store(consent_router, request.state.identity)
        refl = _goals.add_reflection(store, pid, payload.get("text", ""))
        resp = {"ok": True, "pseudo_id": pid, "reflection": refl}
        if refl and refl.get("floor") == "distress":  # Slice G: surface the frame
            resp["distress_support"] = _distress.frame_from_settings(settings)
        return resp

    @api.post("/overlay", dependencies=[Depends(authorize)])
    def overlay(request: Request, payload: dict = Body(...)):
        """Set/replace the learner's customization overlay (opt-in; null/empty clears).
        Same PII boundary; pseudonymous id only. Input, never authority: the overlay is
        floor-checked and normalized server-side and can never loosen a floor."""
        try:
            assert_no_pii(payload)
        except PIIRejected as e:
            raise HTTPException(422, f"PII rejected at boundary: {e}") from e
        pid = request.state.identity.learner_id
        if "consent" in payload and type(payload["consent"]) is not bool:
            raise HTTPException(422, "consent must be boolean")
        register(consent_router, request.state.identity, payload.get("consent", False))
        store = scoped_store(consent_router, request.state.identity)
        artifact = _overlay.set_overlay(store, pid, payload.get("overlay"))
        return {"ok": True, "pseudo_id": pid, "overlay": artifact}

    @api.post("/events", dependencies=[Depends(authorize)])
    def events(request: Request, payload: dict = Body(...)):
        """Webhook ingress (e.g. an async gradingspec_result or workspace event).

        PII-checked and acknowledged; there is NO grade-write side effect."""
        try:
            assert_no_pii(payload)
        except PIIRejected as e:
            raise HTTPException(422, f"PII rejected at boundary: {e}") from e
        return {"ok": True, "protocol": PROTOCOL_VERSION, "received": payload.get("type", "event")}

    return api


def _default_consent_router() -> ConsentRouter:
    durable = SqlStore() if settings.store_backend == "sql" else InMemoryStore()
    return ConsentRouter(durable)


def default_router() -> APIRouter:
    """The /quad/v1 router wired from config, for mounting on the main app."""
    return build_router(_default_consent_router(), get_active_pack(), get_llm)
