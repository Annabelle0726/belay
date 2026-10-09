# Front-end

Reference front-ends for the Sol peer-tutor backend. They are demos and pilot
glue; the backend is the source of truth. Request lifecycle behavior is covered
by offline transport and page-script tests, not authenticated browser acceptance.

| File | Purpose |
|------|---------|
| `widget.html` | The reference widget (Slice E/F), wired to the `/quad/v1` sidecar. Drop-in embeddable; routes entirely through the backend (no browser-side key). |
| `embed-demo.html` | A minimal page showing how to embed the widget on a host site. |
| `dev-client.html` | Zero-dependency page that routes through the backend to verify a deployment. Marked DEV ONLY: uses a hardcoded `PID = "p_dev"` without consent registration, so it is not suitable for a pilot session. |
| `api-client.js` | A small API client (`runModel`, `solTurn`, `createParticipant`, `exportEvents`, `getCurriculum`) for a custom front-end. |
| `request-lifecycle.js` | Shared bounded JSON transport, turn validation, and page-local duplicate/stale-response protection. |

## Failure and waiting behavior

The reference pages and API client bound JSON requests to 90 seconds, including
reading the response body, with no automatic retries. The browser may stop
waiting while server/provider work continues; this is not a cancellation feature.
Malformed JSON, empty messages and unusable display metadata cannot become a
successful tutor answer. An ambiguous network/timeout/5xx failure explains that
execution may still be running and directs the learner to course support.

The pages block repeat clicks while work is pending and after an uncertain outcome
in that page's current learner/exercise context. Context changes fence late
responses, including switching away and back. A failed run never starts an Ask
with stale run data. The widget preserves unsent text on failure and does not put
error/empty tutor messages in dialogue history. No learner cancellation button
is added.

These are local guards, **not HTTP idempotency or durable recovery**. A refresh,
another tab or another device is not protected by the page-local gate. Do not
reload/resubmit to resolve an unknown outcome; the authenticated job/status API
is the next prerequisite for recovering the same operation. The API client
reports `error.code` and `error.uncertain`; custom hosts must implement their own
display/in-flight guard and must not automatically retry uncertain POSTs.

Run the offline tests from the repository root (no backend/model endpoint):

```text
node --test frontend/tests/control-messages.test.cjs frontend/tests/request-lifecycle.test.cjs frontend/tests/turn-pages.test.cjs
```

The page tests execute the actual inline page scripts with a minimal DOM harness
and mocked transport. Real browser/authenticated HTTP acceptance remains pending.

## Backend wiring

`api-client.js` talks to the backend with two calls:

1. Run a submission: `runModel(participantId, exerciseId, src)` posts to `/api/run`,
   which executes the submission in the sandboxed runner and grades it server-side.
2. Ask the tutor: `solTurn({...})` posts to `/api/sol/turn`, which runs the full
   evaluation-first loop server-side and returns the Sol turn. No browser-side model
   key and no direct provider fetch.

Set the backend origin before loading the client (otherwise it defaults to
`http://localhost:8000`):

```js
window.SOL_BACKEND_URL = "https://your-host"
```

Stance is assigned per enrollment URL (`?stance=peer|oracle|control`, default `"peer"`)
and held constant for the session. It is the RQ2/H2 manipulated variable, not a
student-facing toggle.

## Glass-box telemetry (rendered per turn)

A front-end renders the `solTurn` response. Top-level fields drive the five stage
cards; the richer `components` block backs the same cards and the research trace.

| Field | Stage | Notes |
|-------|-------|-------|
| `affective_state` | Peer-Reasoner | one of `AFFECT` (flow, productive_struggle, curious, confusion, frustration, disengaged) |
| `intervention` | Peer-Reasoner | one of `INTERV`, including `encourage` (meta-affective, 5c) and `revisit` (spaced check, 5e) |
| `confidence` | Self-Evaluation | calibrated read, 0 to 1 |
| `governance` | Governance | one of `GOV` (withholding_solution, redirect_answer_seeking, encourage_tone, flag_escalate) |
| `memory.grasped` / `memory.shaky` | Memory | free-text concept tags from this turn |
| `components.learner_model` | Memory | persistent 5e model: `{ n_grasped, n_shaky, revisit_concept, shaky_concepts, due_review }`. `null` on the control arm, so the UI hides the learner-model chips. When `intervention === "revisit"`, the `revisit_concept` is shown as a chip (human label via `CONCEPT_LABELS`, raw id in the `title` tooltip). |

Export button: downloads `GET /api/session/{pid}/events.jsonl` (the durable 6 trace,
consenters only).
