"""Request schemas for the Quad sidecar. PII is rejected by `pii.assert_no_pii`
on the RAW body before these parse, so the models stay permissive."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class QuadDialogueTurn(BaseModel):
    who: str
    text: str


class QuadTurnRequest(BaseModel):
    # extra="allow" so any stray (potentially PII) field is captured rather than
    # silently dropped; the raw body is PII-checked before this parses.
    model_config = ConfigDict(extra="allow")

    pseudo_id: str                       # pseudonymous host id, e.g. "gh:12345"
    exercise_id: str
    source: str = ""
    event: str = "chat"
    mode: str = "study"
    stance: str = "peer"
    recent: List[QuadDialogueTurn] = []
    signals: Optional[dict] = None
    # OPTIONAL per-learner customization overlay (bounded knobs). Input, never
    # authority: floor-checked + normalized like goals; cannot loosen the leak or
    # wellbeing floor. Carried on the turn and persisted where goals ride.
    overlay: Optional[dict] = None
    # READ-ONLY context. A Quad gradingspec run result maps onto the pack's run
    # result (the §1 gradingspec convergence). There is NO write path back.
    gradingspec_result: Optional[dict] = None
    consent: bool = False                # DMP §3 event-trace gating; default ephemeral
