# Quad tutor-seam protocol — `/quad/v1`

The peer-tutor framework exposes its evaluation-first tutor loop to the EduCloud
**Quad** control plane through a small, versioned HTTP/JSON **sidecar**
(`backend/app/integrations/quad/`). The sidecar adds **no** pedagogical or
governance decision of its own — it is a thin, privacy-enforcing adapter over the
existing loop. It is **Apache-2.0-compatible** and imports framework **core only**
(`app.agent`, `app.core`, `app.store`, `app.config`), never a domain `pack`
(enforced by `tests/test_import_boundaries.py`). It plugs into Quad's `pkg/tutor`
seam.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/quad/v1/health` | liveness + protocol/pack/provider |
| GET | `/quad/v1/capabilities` | declared identity scheme, grades posture, stances, routes, license |
| POST | `/quad/v1/turn` | run **one** tutor turn over the existing loop |
| POST | `/quad/v1/events` | webhook ingress (e.g. an async gradingspec result / workspace event); PII-checked, acked |

`GET /quad/v1/capabilities` is the discovery document; it advertises
`identity.scheme = "pseudonymous"`, `grades = {mode: "read-only", writes: false}`,
`instructor_surfaces = "class-level aggregates only"`, the available `stances`,
and `license = "Apache-2.0"`.

## Identity contract — pseudonymous only

The **only** identity the sidecar accepts is a pseudonymous host id: the host's
**numeric user id namespaced by provider**, e.g. `gh:12345` (pattern
`^[a-z0-9_]+:[0-9]+$`). This `pseudo_id` **is** the participant anon-code namespace
in the store; no separate identity is created.

**PII is refused at the boundary** (`pii.assert_no_pii`, HTTP 422). Rejected:
- any field key (anywhere in the payload) naming a person or institutional id —
  `name` / `first_name` / `last_name` / `full_name` / `*_name`, anything containing
  `sis`, `student`, `email`, `mail`, `ssn`, or `phone`;
- a plaintext **email** pattern in any value except the pedagogical `source`
  (student code may legitimately contain an `@`);
- a `pseudo_id` that is not a bare `provider:numeric-id`.

This mirrors the EduCloud posture: *real names and SIS IDs never reach the
server*; the tutor sees a pseudonymous id + submission content only. Instructor
surfaces are class-level aggregates; there are no student-vs-student leaderboards.

## Grades firewall — read-only, no write path

A Quad-run grading result may be supplied to a turn as **`gradingspec_result`**.
It is **read-only context only**: the sidecar maps it onto the turn's run-result
slot so the tutor can ground its guidance in "did it pass / what's the metric",
and **nothing more**. There is:
- **no route** that writes a grade (the surface is exactly the four routes above);
- **no write path** from the sidecar to any grading surface;
- **no grade field** echoed back in the turn response.

The tutor **never writes to grades** — tutoring is formative only. This is
tested (`tests/test_quad_sidecar.py`: `test_gradingspec_result_is_read_only_context`,
`test_no_grade_write_route_exists`, `test_sidecar_source_has_no_grade_write_calls`).

## gradingspec convergence (from Phase 1)

A Quad `pkg/gradingspec` run produces a host-neutral grading verdict. That verdict
maps **directly** onto the framework's pack run-result envelope (§6): the
pack-agnostic top level — `{ok, goalMet, metric, error, pack}` — is exactly what a
gradingspec result expresses (did it run, did it meet the goal, the primary
scalar). The DS pack's declarative spec checks (`packs/datascience/specs/*.json`,
documented in `specs/GRADING_SPEC.md`) were built to be convergent with
`pkg/gradingspec` for this reason: a Quad-run grading result drops into
`gradingspec_result` and the tutor reads it as native context — no translation
layer. Governance is unaffected: the deterministic leak gate reads the pack's
`leak_evidence`, never the grade.

## POST `/quad/v1/turn` — request

```jsonc
{
  "pseudo_id": "gh:12345",          // REQUIRED, pseudonymous host id
  "exercise_id": "ds-foundations",  // resolved via the active pack
  "source": "import pandas as pd\n...",
  "event": "chat",                  // run | chat
  "mode": "study",                  // study | teach
  "stance": "peer",                 // peer | oracle | control
  "recent": [{"who": "student", "text": "..."}],
  "signals": { "attempts": 2, "repeatedError": false },
  "gradingspec_result": {           // OPTIONAL, READ-ONLY context
    "ok": true, "goalMet": false, "metric": 0.4,
    "pack": {"id": "datascience", "summary": "r2=0.40"}
  },
  "consent": false                  // DMP §3 event-trace gating (default ephemeral)
}
```

The response is the standard tutor-turn object (affect, intervention, governance
flag, message, `components` telemetry) — identical to `POST /api/sol/turn`. The
sidecar exposes the loop; it does not relitigate any decision.

## Versioning

The protocol is versioned in the path (`/quad/v1`). §6 schema additions are
additive and the `events.jsonl` export contract is stable, so a `v1` integration
keeps working as the trace grows.
