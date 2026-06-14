# Front-end

Two front-ends share one backend:

| File | Purpose |
|------|---------|
| `dev-client.html` | Zero-dependency page that routes entirely through the backend (no browser-side key). Use it to verify a deployment. Marked **DEV ONLY**: uses a hardcoded `PID = "p_dev"` without consent registration — not suitable for a pilot session. |
| `quantum-inventioneers-peer-tutor.jsx` | The rich React artifact — **already wired to the backend** as of v0.1.0-pilot. The in-browser Anthropic key and direct model call have been removed. See mode flags below. |
| `api-client.js` | The API client used by the artifact (`runModel`, `solTurn`, `createParticipant`, `exportEvents`). |

## Current wiring status — DONE

Both "swaps" from the original wiring plan have been applied to
`quantum-inventioneers-peer-tutor.jsx`:

1. **Execution** — `run(src, target, tol)` → `runModel(participantId, exerciseId, src)`
   via `api-client.js`. The response shape is identical.

2. **The tutor** — `askSol(payload)` → `solTurn({...})` via `api-client.js`.
   The response shape is identical; the `components` block adds richer telemetry.
   No in-browser model key. No `api.anthropic.com` fetch.

## Glass-box telemetry (rendered per turn)

The right-hand "glass box" renders the `solTurn` response. Top-level fields drive the
five stage cards; the richer `components` block backs the same cards and the research trace.

| Field | Stage | Notes |
|-------|-------|-------|
| `affective_state` | Peer-Reasoner | one of `AFFECT` (flow · productive_struggle · curious · confusion · frustration · disengaged) |
| `intervention` | Peer-Reasoner | one of `INTERV` — incl. `encourage` (meta-affective §5c) and `revisit` (spaced check §5e) |
| `confidence` | Self-Evaluation | calibrated read, 0–1 |
| `governance` | Governance | one of `GOV` (withholding_solution · redirect_answer_seeking · encourage_tone · flag_escalate) |
| `memory.grasped` / `memory.shaky` | Memory | free-text concept tags from this turn |
| `components.learner_model` | Memory | persistent §5e model: `{ n_grasped, n_shaky, revisit_concept, shaky_concepts, due_review }`. **`null` on the control arm** — the UI hides the learner-model chips. When `intervention === "revisit"`, the `revisit_concept` is shown as a chip (human label via `CONCEPT_LABELS`, raw id in the `title` tooltip). |

## Mode flags (set before loading the bundle)

```js
window.QI_BACKEND_URL = "https://your-host"  // BACKEND=true: full wired path
window.QI_OFFLINE = true                      // OFFLINE=true: local simulator, Sol unavailable
// neither set                                // shows a configuration notice; run/Sol disabled
```

- **BACKEND=true**: onboarding consent screen → `POST /api/participant` → full session.
- **OFFLINE=true**: local circuit simulator only; Sol returns "not available offline".
- **Default (neither)**: UI shows a banner and disables run/Sol; prompts to configure.

Stance is assigned per enrollment URL (`?stance=peer|oracle|control`, default `"peer"`)
and held constant for the session — it is the RQ2/H2 manipulated variable, not a
student-facing toggle.

Export button: in BACKEND mode downloads `GET /api/session/{pid}/events.jsonl`
(durable §6 trace, consenters only); otherwise exports the local interaction log.
