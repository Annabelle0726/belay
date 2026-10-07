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

## Optional saved dialogue

`conversation-client.js` supplies an authenticated Session for both API surfaces.
`api-client.js` exports `createConversationSession(exerciseId, onChange)`. The three
demos mount the same minimal saving/history controls without changing their CSS
or page layout. The server config response supplies the VERIFIED namespace and
current granted exercise versions; browser inputs never grant access.

Saving is unchecked until the learner opts in under an enabled institution policy.
The notice shows policy_id and creation-based retention. When saving is disabled,
ordinary tutoring uses the existing unsaved API. A new saved attempt is explicit;
refresh restores its latest bounded page. Older pages, a new attempt and deletion
are explicit actions. Missing/expired/deleted history clears the stale pointer and
does not silently create a replacement. Pending/failed turns are labeled. Turning
saving off stops saving new turns; it does not delete existing history. Deletion
remains available for an existing pointer even while the saving preference is off.

Browser localStorage holds only the attempt ID, saving preference and occasionally
a pending creation request ID, namespaced by verified institution/class/learner,
backend/API prefix and exercise/version. It contains no credentials, source,
learner/assistant messages or retry body. A turn request and its request_id remain
in RAM during a lost-response retry. Refresh obtains authoritative server history;
it never submits invented assistant messages. Sensitive exchanges restore neutral
placeholders; the current live institution support response can still be displayed.

The host must update its learner/class/institution values and dispatch
`window.dispatchEvent(new Event("belay-auth-changed"))` on login/logout or scope
change; discard/recreate embedded sessions when changing hosts. The shared controls
clear prior history and discard an obsolete session's late response. Each saved
operation additionally checks the authenticated server namespace. No token belongs
in URL parameters, browser persistence, logs or exports.

Hermetic checks: `node --test frontend/tests/auth-client.test.cjs
frontend/tests/conversation-client.test.cjs` (13 passed). These exercise refresh,
new attempts, lost-response retries, pagination, unavailable/deleted history,
identity changes and credential headers, plus parse every demo inline script.
