# INSTRUCTOR_MODE — design spec

Status: **design, pre-implementation.** This document specifies instructor
mode so a build session can start from decisions rather than a blank page.
Target: an instructor-mode **alpha by end of August 2026** (Line E, E0 first
builds), **live for the single-course pilot** later in the fall term (E1).
Every constraint below cites its in-tree source, per house convention.

## 1. What exists today, and the gap

There is no authenticated role or privileged mode: the API has no auth
dependency on any route, and "instructor" appears only as prompt wording and
the `flag_escalate` label ("Flagged for instructor").
Source: `ROADMAP.md` (Instructor mode), `backend/app/main.py` (no auth
dependency on the routes), `backend/app/agent/orchestrator.py` (the label).

What the architecture already gives us, which the design leans on rather than
reinvents:

- **Pseudonymous identity only.** Participants are pseudonymous host ids
  (`gh:12345`) with a consent flag; no PII exists in the identity model, and
  the Quad sidecar rejects PII at the boundary with a 422.
  Source: `PRIVACY.md` (Privacy by architecture),
  `backend/app/store/models.py`, `backend/app/integrations/quad/pii.py`.
- **A content-free, append-only trace.** Every event is the fixed eight-field
  row; verbatim learner text is never written; `event_type` values are
  additive without changing the row shape or the `events.jsonl` contract.
  Source: `PRIVACY.md` (Content-free trace; Fixed trace row),
  `backend/app/store/repository.py` (`make_event`).
- **Escalation already exists as trace, not as a surface.** Governance can
  end a turn in `flag_escalate`; distress turns log
  `governance="flag_escalate"` with a content-free payload
  (`{triggered, configured, routed}`). What is missing is any place an
  instructor can see that these events occurred.
  Source: `backend/app/agent/governance.py` (flag values),
  `backend/app/agent/orchestrator.py` (`_distress_turn`), `PRIVACY.md`
  (distress trace).
- **The grades firewall and the goals/reflections exclusion.** Grading
  results are read-only turn context with no write path, and goals and
  reflections are pseudonymous and never surfaced to an instructor. These are
  standing commitments this design must preserve, not options.
  Source: `PRIVACY.md` (Grades firewall), `backend/app/agent/goals.py`.

**One live exposure this design closes:**
`GET /api/session/{pid}/events.jsonl` is unauthenticated today — anyone
holding a pseudonymous id can pull that participant's full trace. The trace
is content-free by construction, but the export is research data and belongs
behind the instructor role.
Source: `backend/app/main.py` (the route, no dependency).

## 2. Design decisions

### D1 — Authentication is a pluggable dependency with two providers

One FastAPI dependency (`require_instructor`) guards every instructor route.
Two providers behind it, selected by config:

- `token` (standalone / alpha): a static bearer token from
  `INSTRUCTOR_TOKEN`; unset means instructor mode is **off** and every
  instructor route returns 404. Enforcement by config absence, matching the
  platform's sensitivity discipline.
- `oidc` (EduCloud): verify a JWT against the Waypoint Keycloak issuer
  (JWKS), require the `instructor` role claim, and read the course binding
  from a claim. This is the module's bring-your-own-OIDC seam from
  SYSTEM.md contract 3; module-local token auth is the standalone fallback,
  not the platform path.

The dependency is deterministic and runs before any handler — the same
layer-ordering rule the rest of the platform uses. No model is ever involved
in an authorization decision.

### D2 — Roles are two, and instructor is course-bound

`student` (the existing unauthenticated surface, unchanged in alpha) and
`instructor`. In alpha the instructor is bound to one course by configuration
(`INSTRUCTOR_COURSE_LABEL`, an opaque attribution label per SYSTEM.md
contract 1). Multi-course and multi-instructor binding arrives with Keycloak
claims at institutional scale (E3), as config, not code.

### D3 — The instructor surface is deterministic and content-free

Alpha exposes four read surfaces and one action, all under `/instructor/*`,
all behind `require_instructor`, none making a model call:

1. `GET /instructor/escalations` — the queue. Rows are drawn from the events
   trace where the turn ended in `flag_escalate` (governance or distress):
   pseudonymous participant id, timestamp, exercise id, event type, and the
   content-free payload. Nothing else exists in the trace to leak, which is
   the point of the fixed row.
2. `POST /instructor/escalations/{event_ref}/ack` — the action. Appends an
   additive `instructor_ack` event to the same trace (append-only, fixed row
   shape preserved; `event_type` additivity is the documented contract). No
   update-in-place, no new table.
3. `GET /instructor/measures` — cohort/exercise aggregates from the existing
   process-measures layer (`measures_by_attempt` already carries `cohort`).
   Aggregates only, with a suppression floor: any cell with n below 5 is
   withheld, so small-cohort aggregates cannot re-identify a pseudonym.
4. `GET /instructor/status` — operational state: active DomainPack, corpus
   stats, `distress_configured`, and whether routing is enabled. Mirrors
   what the operator can already see from config; read-only.
5. `GET /api/session/{pid}/events.jsonl` — moves behind `require_instructor`
   (the exposure in §1).

### D4 — What instructor mode never surfaces (the floor, restated as tests)

- Goals and reflections: no instructor endpoint returns them, links to them,
  or aggregates over their content. This is a schema-level exclusion with a
  canary test, not a filter.
- Verbatim learner text: structurally absent from the trace already; the
  instructor surface adds no new capture.
- Grades: the firewall is untouched; instructor mode adds no read of grading
  results and, as everywhere, no write path exists.
- Distress detail: the queue shows that a distress escalation occurred and
  its `{triggered, configured, routed}` payload — never message content,
  which is never stored anyway.

### D5 — No new model calls in alpha

Instructor-facing AI (summaries, suggested interventions) is one of Line E's
three Portage consumers and will route through Portage under instructor-lane
policy when it exists — but it is **out of scope for alpha**, because it
would put model output in front of an instructor without an eval gate.
Everything in D3 is a deterministic read of existing records.

### D6 — Naming debt is noted, not fixed here

`/api/sol/turn` carries the prior module name in a route path. Renaming an
API path is a breaking change and belongs to the publish-step atomic rename
(`README.md` note), not to this slice.

## 3. IRB note

Instructor visibility of escalation events is a change to the IRB-facing
posture. `PRIVACY.md` gains a section when this ships: who can see the
escalation queue, that it is content-free, the suppression floor on
aggregates, and the auth model. Mark as a standing IRB item until reviewed,
per that document's convention.

## 4. Test plan (hermetic, in-tree style)

- **Authz matrix:** every `/instructor/*` route returns 401 with no
  credential, 403 with a student credential, 200 with the instructor token;
  with `INSTRUCTOR_TOKEN` unset, all return 404. The dependency fires before
  any handler (deterministic-layer-first, asserted the same way the
  classifier layer is).
- **Exposure regression:** `events.jsonl` unauthenticated returns 401; the
  pre-auth behavior is locked out by test.
- **Privacy floor:** a canary posts a goal and a reflection, then every
  instructor endpoint is walked and asserted to contain neither the content
  nor any reference to it. Response schemas are asserted field-by-field.
- **Suppression floor:** an aggregate over a cohort of n=4 returns the
  withheld marker, n=5 returns numbers.
- **OIDC provider:** stub JWKS fixture; expired token, wrong role, wrong
  course claim each rejected. No network in any test.
- mypy ratchet held; `uv run pytest` green without network or model calls.

## 5. The build session (paste-ready scope)

Two sessions, in order. Constraints for both: no new tables (append-only
events with additive types), no model calls, no change to the leak gate or
the wellbeing floor, PRIVACY.md updated in the same diff as the behavior it
describes, VALIDATION.md slice entry recorded per house convention.

**Session A — the seam.** `require_instructor` with `token` + `oidc`
providers and the 404-when-unset rule; gate `events.jsonl`; the authz-matrix
and exposure tests. Accept: matrix green, exposure locked, ratchet held.

**Session B — the surface.** Escalation queue + ack event, measures
aggregates with the suppression floor, status endpoint, and a minimal
`frontend/instructor.html` in the existing widget style (token entry in
alpha; OIDC redirect at E1 when Waypoint's Keycloak is live). Accept: a
seeded `flag_escalate` event appears in the queue and can be acked; the
privacy-floor canary passes; the page works against a local backend.

Alpha is both sessions done. Pilot-live (E1) adds only configuration: the
`oidc` provider pointed at the Waypoint realm and the course label bound to
the real pilot course.
