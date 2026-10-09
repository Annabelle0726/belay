# Front-end

Reference front-ends for the Sol peer-tutor backend. They are demos and pilot
glue, not part of the tested framework; the backend is the source of truth.

| File | Purpose |
|------|---------|
| `widget.html` | The reference widget (Slice E/F), wired to the `/quad/v1` sidecar. Drop-in embeddable; routes entirely through the backend (no browser-side key). |
| `embed-demo.html` | A minimal page showing how to embed the widget on a host site. |
| `dev-client.html` | Zero-dependency page that routes through the backend to verify a deployment. Development demo; the host must supply an authorized learner alias and signed access token. |
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

## Host credential contract (production phase 1)

The four clients use `auth-client.js` for authenticated API calls. The host must
install these values before loading/calling the client (including demos):

```js
window.BELAY_AUTH_ORIGIN = "https://belay.your-institution.example";
window.BELAY_GET_ACCESS_TOKEN = async () => hostSession.getShortLivedAccessToken();
window.BELAY_LEARNER_ID = "gh:12345"; // dev-client alias; must match server grants
window.BELAY_INSTITUTION_ID = "institution-opaque-a"; // both selectors required
window.BELAY_CLASS_ID = "class-opaque-a";             // for multi-class subjects
```

The host issues RS256 credentials with a lifetime <=15 minutes and owns refresh.
The callback keeps credentials in memory; it is never obtained from a query string
or saved to browser storage. No model/provider key belongs in the frontend. The
helper refuses a backend origin other than `BELAY_AUTH_ORIGIN`; HTTPS is required
except for loopback development. If the demo backend field changes, requests fail
until the trusted host explicitly updates the allowed origin. Configure CORS for
that host. Body aliases must match the authorized learner; registration returns
that same alias. `exercise_version` can be sent to pin an assignment version;
omitting it uses the server's deployed version and still requires its grant.
All existing UI structure remains unchanged. See
[the server contract](../docs/authentication.md) and run
`node frontend/tests/auth-client.test.cjs` for hermetic credential wiring checks.

## Standalone local demo

A plain `python -m http.server` cannot supply the host credential callback above.
For an explicit local-only demo, stop the existing frontend and backend with
Ctrl+C, then run from `backend/` using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_demo
```

Open `http://127.0.0.1:5173/dev-client.html`. This one command starts both servers
on loopback, generates a temporary RSA key and synthetic class grant, and injects
the host callback before the client loads. Access tokens are minted on demand for
five minutes and stay in memory; the private key is never written or served. The
backend still verifies signatures and membership, uses `BELAY_ENV=local` and an
ephemeral memory store, and reads the inference settings from `backend/.env` when
present. Asking the peer tutor still requires your configured model endpoint.
Existing `.env` files and deployment configuration are not changed.

If the original servers should keep running, choose different ports:

```powershell
.\.venv\Scripts\python.exe -m scripts.local_demo --frontend-port 5174 --backend-port 8001
```

Then open `http://127.0.0.1:5174/dev-client.html`. For the no-model embed demo use
`--pack _skeleton` and open `/embed-demo.html` (control stance). Ctrl+C stops both
child/demo servers and removes the temporary public key and grants. The helper is
only a local host emulator, never a production identity provider. Production and
normal static hosting continue to require the real host credential callback.
