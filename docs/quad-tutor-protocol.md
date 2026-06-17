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
| POST | `/quad/v1/goals` | set/clear the learner's own goals (opt-in; pseudonymous) |
| POST | `/quad/v1/reflection` | record a learner reflection (opt-in; pseudonymous) |
| POST | `/quad/v1/overlay` | set/clear the per-learner customization overlay (opt-in) |
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
  "overlay": {                      // OPTIONAL per-learner customization (bounded)
    "persona":  {"tone": "direct", "verbosity": "balanced", "framing": "peer"},
    "pedagogy": {"scaffolding": "less", "stretch": "high"},
    "accommodation": {"reading_level": "plain", "language": "en"}
  },
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

## Per-learner customization overlay — input, never authority

A host (or a learner-facing control) may shape **how** the tutor helps via a
**bounded, enumerated** overlay. It may be sent inline on a `/quad/v1/turn` or set
once via `POST /quad/v1/overlay` (and is persisted on the learner state alongside
goals). It is **input, never authority**: it is floor-checked and normalized
server-side and can never loosen a floor. Fields (each defaults mastery-friendly, so
an absent overlay reproduces today's behavior):

| Section | Knob | Values (default first) |
|---|---|---|
| persona | tone | `warm`, `neutral`, `direct` |
| persona | verbosity | `balanced`, `brief`, `detailed` |
| persona | framing | `peer`, `coach` |
| pedagogy | scaffolding | `default`, `more`, `less` |
| pedagogy | stretch | `default`, `low`, `high` |
| accommodation | reading_level | `default`, `plain`, `advanced` |
| accommodation | language | short locale token, e.g. `en`, `es` |

**Why enumerated, not a free-form stance string.** A free-form stance is a
wellbeing-floor bypass risk and a prompt-injection surface; enumerated knobs are safe
by construction, because only a **framework-authored phrase keyed by the chosen enum**
ever reaches the prompt — never the learner's raw text. Floor guarantees a host can
rely on:

- **The leak floor is not customizable.** No knob yields more of the answer or trades
  mastery for answers; `scaffolding: less` means *more independence / fewer hints*, not
  more solution. The deterministic leak gate is supreme over any overlay, exactly as
  over a goal (`tests/test_overlay.py::test_leak_floor_not_customizable_by_overlay`).
- **The wellbeing floor binds the overlay.** Every submitted value is run through the
  same `goals.is_harmful` detector; a harm-requesting field ("be harsh with me",
  "never let me rest") is **declined** (recorded, dropped to default, never honor-framed)
  exactly like a harmful goal, and a value that is not a recognized safe token is
  dropped to the default — so harmful text never reaches the prompt as instruction. A
  worst-case model that tries to honor a harmful overlay is still caught on the OUTPUT
  by the post-hoc berating softener (`telemetry.components.wellbeing_softened`), the
  same defense-in-depth as goals (EXTRACTION_PLAN §(g)).
- **Declines are observable.** `telemetry.components.overlay_declined` lists which
  submitted fields the floor check declined this turn (never the raw value).

`POST /quad/v1/overlay` accepts `{pseudo_id, overlay, consent?}`, holds the same PII
boundary (422), and returns the normalized artifact. `capabilities.customization`
advertises the field vocabulary and that the floors are not customizable.

## Embed contract — drop-in, never authenticates

A host mounts the tutor with an already-authenticated pseudonymous learner id; the
embed **never performs auth and never handles PII**. The framework owns the contract
and a **replaceable reference rendering**; the host owns auth, roster, and persistence.

- **Reference widget:** `frontend/widget.html` — a single-file, dependency-light,
  drop-in (or iframe-able) widget that points at the sidecar with host-supplied
  pseudonymous context. Three panes (chat, goals + reflection, trace + signals) plus
  one customization knob (scaffolding). It renders **signals, not verdicts** (a withheld
  solution shows as "held back, with a nudge"; self-eval and the wellbeing softener are
  observable indicators) and shows **no grades and no rankings**. Replace it wholesale
  with the host's own shell against the same `/quad/v1` contract.
- **Minimal demo:** `frontend/embed-demo.html` — one `/quad/v1/turn` against the
  `_skeleton` pack, for a no-model smoke.
- **What the host supplies:** `pseudo_id` (pseudonymous, e.g. `gh:12345`),
  `exercise_id`, `stance`, dialogue `recent`, and optionally an `overlay`. **What the
  host must not send:** names, SIS ids, email, or any PII (refused at the boundary,
  422). The host renders nothing it is not given; there is no grade or rank in the
  response to render.

## Deployment as an EduCloud Registry agent object

The framework ships as a cleanly deployable **agent object** — the deployment-layer
half of the compute-agnostic story. (We build the framework's own deployability,
**not** the Registry or the Coolify adapter — those are the EduCloud Registry
workstream.)

- **Container + one-command bring-up.** `backend/Dockerfile` + root
  `docker-compose.yml` stand the tutor up with **SQLite by default** (no DB
  service required) and **`PROVIDER=openai_compatible`**, ready to point at a local
  or institutional model endpoint via `OPENAI_BASE_URL` — no lock-in:
  ```bash
  docker compose up --build          # SQLite + openai_compatible
  docker compose --profile postgres up --build   # opt-in Postgres (for scale)
  ```
- **Preflight doctor.** `python -m app.preflight` verifies config, store
  reachability, and provider-endpoint reachability before serving (the container
  CMD runs it informationally).
- **Registry agent object.** The running container registers as a Registry agent
  object: its `GET /quad/v1/capabilities` IS the discovery document (protocol
  version, pack, provider, identity scheme, grades posture, stances, license), and
  `GET /quad/v1/health` is the liveness probe. The Registry deploys the object
  **through the Coolify adapter**; the resulting **`deployed_url`** is recorded
  back onto the Registry object, and Quad addresses `/quad/v1/turn` at that URL.
  The framework exposes the object and its health/capabilities; the Registry +
  Coolify adapter own the deploy mechanics.

## FERPA posture

With a **self-hosted provider** (`PROVIDER=openai_compatible` pointed at a local or
institutional model endpoint), the deployed tutor keeps **student code and tutor
prompts on institutional compute** — there is no external model API in the data
path. Combined with the pseudonymous-only identity (no names/SIS/email ever reach
the server) and the read-only grades firewall, the deployment keeps PII and
student work inside the institution's boundary. Self-hosted inference is a privacy
*strengthener*, not a new off-box data path.

## Distress routing (pre-go-live, optional, IRB-owned)

Distress routing is **off by default**. If you enable it (`DISTRESS_ROUTING_ENABLED=true`),
you **must** also set `DISTRESS_SUPPORT_MESSAGE` and `DISTRESS_ESCALATION_TARGET` to your
institution's IRB- and jurisdiction-approved resources. Enabling routing **without**
configuring those is a pre-go-live **misconfiguration**: the tutor would render only a
safe generic frame with no institution-specific resources. App startup and
`python -m app.preflight` emit a prominent operator WARNING in exactly that state, so it
is caught in deployment testing rather than at a learner's first triggered turn. The
detector is a **narrow net and a supplement to human channels, never the primary
safeguard** — false negatives are expected; it routes toward people, it does not replace
them. See `docs/PRIVACY.md`. The framework invents no hotline, number, or service.

## Versioning

The protocol is versioned in the path (`/quad/v1`). §6 schema additions are
additive and the `events.jsonl` export contract is stable, so a `v1` integration
keeps working as the trace grows.
