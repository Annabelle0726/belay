# Front-end

Reference front-ends for the Sol peer-tutor backend. They are demos and pilot
glue, not part of the tested framework; the backend is the source of truth.

| File | Purpose |
|------|---------|
| `widget.html` | The reference widget (Slice E/F), wired to the `/quad/v1` sidecar. Drop-in embeddable; routes entirely through the backend (no browser-side key). |
| `embed-demo.html` | A minimal page showing how to embed the widget on a host site. |
| `dev-client.html` | Zero-dependency page that routes through the backend to verify a deployment. Marked DEV ONLY: uses a hardcoded `PID = "p_dev"` without consent registration, so it is not suitable for a pilot session. |
| `api-client.js` | A small API client (`runModel`, `solTurn`, `createParticipant`, `exportEvents`, `getCurriculum`) for a custom front-end. |

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
