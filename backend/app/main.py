# SPDX-License-Identifier: AGPL-3.0-only
"""
FastAPI surface for the peer-tutor framework.

Routes
  GET  /healthz                          liveness
  GET  /api/curriculum                   modules + exercises
  POST /api/run                          compile + execute + grade; logs a run event
  POST /api/sol/turn                     the evaluation-first peer loop
  POST /api/participant                  create/record consent (anonymized)
  GET  /api/session/{pid}/events.jsonl   export the §6 trace for analysis
  /quad/v1/*                             Quad tutor-seam sidecar (integrations/quad)

The active domain pack (TUTOR_PACK), store (memory|sql), and LLM client are
selected from config so the same app runs offline for dev or wired to the real
platform for a pilot.

Consent gating (DMP §3 / IRB)
  Every participant gets a durable Participant row regardless of consent.
  Events + LearnerState are routed via ConsentRouter:
    consent=True  → durable SqlStore (persists across restarts)
    consent=False → per-session ephemeral InMemoryStore (never persisted)
    unregistered  → ephemeral (fail-safe)
  The trace export reads ONLY the durable store; tutoring behaviour is
  byte-for-byte identical regardless of consent.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .agent import distress as distress_mod
from .agent import get_llm, run_turn
from .agent import goals as goals_mod
from .agent import overlay as overlay_mod
from .auth import authorize, denied
from .config import settings
from .core.registry import get_active_pack
from .schemas import (
    GoalRequest,
    OverlayRequest,
    ParticipantRequest,
    ParticipantResponse,
    ReflectionRequest,
    RunRequest,
    RunResult,
    SolTurnRequest,
    SolTurnResponse,
)
from .store import ConsentRouter, InMemoryStore, SqlStore, make_event
from .store.scoped import ScopedStore, register, scoped_store

app = FastAPI(title="Peer-Tutor Framework", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- wiring (swappable via env) ----------------------------------------------
_durable = SqlStore() if settings.store_backend == "sql" else InMemoryStore()
_router = ConsentRouter(_durable)
_pack = get_active_pack()  # active DomainPack (TUTOR_PACK, default datascience)

# Slice H visibility: at startup, warn (no PII/content) if distress routing is enabled
# but unconfigured, so a half-armed opt-in is caught now, not at the first triggered
# turn. Visibility only — no runtime behavior change.
distress_mod.warn_if_misconfigured(settings)


def _llm():
    # Constructed per-process lazily; uses the configured provider
    # (openai_compatible by default). Raises a clear error if unreachable.
    if not hasattr(_llm, "_inst"):
        _llm._inst = get_llm()  # type: ignore[attr-defined]  # function-attribute memo cache (intentional)
    return _llm._inst  # type: ignore[attr-defined]  # function-attribute memo cache (intentional)


# Quad tutor-seam sidecar: a versioned /quad/v1 surface over the same tutor loop
# (Apache-2.0; pseudonymous identity; grades firewall). See integrations/quad.
from .integrations.quad import build_router as _build_quad_router  # noqa: E402

app.include_router(_build_quad_router(_router, _pack, _llm))


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "pack": _pack.id,
        "provider": settings.provider,
        "store": settings.store_backend,
    }


@app.get("/api/curriculum", dependencies=[Depends(authorize)])
def get_curriculum(request: Request):
    allowed = dict(request.state.identity.active_assignments)
    modules = []
    for module in _pack.curriculum():
        exercises = [
            {**exercise, "exercise_version": allowed[exercise["id"]]}
            for exercise in module["exercises"]
            if exercise["id"] in allowed
        ]
        if exercises:
            modules.append({**module, "exercises": exercises})
    return {"modules": modules}


@app.post("/api/run", dependencies=[Depends(authorize)], response_model=RunResult)
def run(request: Request, req: RunRequest):
    try:
        ex = _pack.get_exercise(req.exercise_id)
    except KeyError:
        raise denied() from None
    result = _pack.run(req.source, ex)
    # Route the trace event to durable or ephemeral based on consent.
    store = scoped_store(_router, request.state.identity)
    store.append_event(
        make_event(
            req.participant_id,
            req.exercise_id,
            "study",
            "run",
            {"source": req.source, "result": result},
        )
    )
    return result


@app.post("/api/sol/turn", dependencies=[Depends(authorize)], response_model=SolTurnResponse)
def sol_turn(request: Request, req: SolTurnRequest):
    try:
        ex = _pack.get_exercise(req.exercise_id)
    except KeyError:
        raise denied() from None
    payload = {
        "participant_id": req.participant_id,
        "exercise": ex,
        "event": req.event,
        "mode": req.mode,
        "stance": req.stance,
        "source": req.source,
        "result": req.result,
        "recent": [t.model_dump() for t in req.recent],
        "signals": req.signals,
        "request": req.request,
        "overlay": req.overlay,
    }
    # Route events + learner-state writes to durable or ephemeral by consent.
    store = scoped_store(_router, request.state.identity)
    try:
        return run_turn(payload, _llm(), store)
    except HTTPException:
        raise
    except Exception as e:  # surface a clean error; the front-end shows a graceful note
        raise HTTPException(502, "tutor unavailable") from e


@app.post("/api/participant", dependencies=[Depends(authorize)], response_model=ParticipantResponse)
def participant(request: Request, req: ParticipantRequest):
    pid = request.state.identity.learner_id
    # Participant row always goes to the durable store (DMP §1).
    # register_participant also updates the in-process consent cache so the very
    # next /api/run or /api/sol/turn in this process sees the correct routing
    # without a round-trip to the DB.
    register(_router, request.state.identity, req.consent)
    return ParticipantResponse(id=pid, anon_code=req.anon_code, consent=req.consent)


@app.get("/api/session/{pid}/events.jsonl", dependencies=[Depends(authorize)])
def export_events(request: Request, pid: str):
    # Export reads ONLY the durable store; non-consenters have no trace by design.
    return Response(
        ScopedStore(_router.durable, request.state.identity).export_jsonl(pid),
        media_type="application/x-ndjson",
    )


# --- learner-authored goals (opt-in; pseudonymous, never PII, never to grades) --


@app.post("/api/goals", dependencies=[Depends(authorize)])
def set_goals(request: Request, req: GoalRequest):
    """Set/update (empty text clears) the student's own goals. Stored
    pseudonymously on the learner model, routed by consent like all learner state."""
    store = scoped_store(_router, request.state.identity)
    artifact = goals_mod.set_goals(store, req.participant_id, req.text)
    resp = {"participant_id": req.participant_id, "goals": artifact}
    if artifact and artifact.get("floor") == "distress":  # Slice G: surface the frame
        resp["distress_support"] = distress_mod.frame_from_settings(settings)
    return resp


@app.get("/api/goals/{pid}", dependencies=[Depends(authorize)])
def get_goals(request: Request, pid: str):
    store = scoped_store(_router, request.state.identity)
    return {"participant_id": pid, "goals": goals_mod.get_goals(store.get_learner_state(pid))}


@app.post("/api/reflection", dependencies=[Depends(authorize)])
def add_reflection(request: Request, req: ReflectionRequest):
    """Record the student's reflection (their own words), linked to their current
    goal. Stored pseudonymously on the learner model; never surfaced to an instructor."""
    store = scoped_store(_router, request.state.identity)
    reflection = goals_mod.add_reflection(store, req.participant_id, req.text)
    resp = {"participant_id": req.participant_id, "reflection": reflection}
    if reflection and reflection.get("floor") == "distress":  # Slice G: surface the frame
        resp["distress_support"] = distress_mod.frame_from_settings(settings)
    return resp


@app.post("/api/overlay", dependencies=[Depends(authorize)])
def set_overlay(request: Request, req: OverlayRequest):
    """Set/replace the learner's customization overlay (opt-in; null/empty clears).
    Bounded knobs only; floor-checked and normalized server-side. Input, never
    authority: it shapes HOW the tutor helps, never loosens a floor. Pseudonymous,
    routed by consent like all learner state; never to grades."""
    store = scoped_store(_router, request.state.identity)
    artifact = overlay_mod.set_overlay(store, req.participant_id, req.overlay)
    return {"participant_id": req.participant_id, "overlay": artifact}
