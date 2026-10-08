# Front-end

Reference front-ends for the Sol peer-tutor backend. They are demos and pilot
glue, not part of the tested framework; the backend is the source of truth.

| File | Purpose |
|------|---------|
| `widget.html` | The reference widget (Slice E/F), wired to the `/quad/v1` sidecar. Drop-in embeddable; routes entirely through the backend (no browser-side key). |
| `embed-demo.html` | A minimal page showing how to embed the widget on a host site. |
| `dev-client.html` | No-build development page with responsive layout, theme and conversation feed; the host supplies an authorized learner alias and signed access token. |
| `dev-client.js` | Authenticated run/turn wiring, live signals and saved/unsaved conversation rendering for the development page. |
| `api-client.js` | A small API client (`runModel`, `solTurn`, `createParticipant`, `exportEvents`, `getCurriculum`) for a custom front-end. |

## Backend wiring

### Authenticated local demo (PowerShell)

`python -m http.server 5173` only serves files. It does not install the host
credential callback, so opening these demos directly reports **Host authentication
is not configured for this backend**. `uvicorn --env-file .env` loads environment
variables into that backend process; it cannot configure the browser.

Stop the old uvicorn and static servers with Ctrl+C in their terminals, then run
one command from `backend` (with the backend dependencies installed):

```powershell
Set-Location C:\Projects\EduCloud-Ecosystem\belay\backend
python -m app.local_dev --save-dialogue
```

Open **http://127.0.0.1:5173/dev-client.html**. The Backend field is automatically
**http://127.0.0.1:8000**. The launcher starts both servers; Ctrl+C stops both.
Do not run the previous two server commands alongside it. For different ports,
pass `--api-port 8001 --frontend-port 5174` and use the printed page URL.

Startup checks both IPv4 and IPv6 loopback listeners: a wildcard or IPv6
server already using either port is a conflict even if an IPv4 bind would succeed
on Windows. This does not stop existing processes; close their terminals or
choose unused ports before starting this demo.

The launcher reads `backend/.env` for model/provider configuration. It supplies
real RS256 credentials valid for five minutes through a same-origin callback,
and a synthetic institution/class/learner grant for the installed pack. Private
keys and bearer tokens stay in memory; credentials never go in a URL or browser
storage. It binds only `127.0.0.1` and refuses foreign Host/Origin/fetch-site
requests. This local issuer is for synthetic development data only; production
still requires the institution's verified identity and authorization contract.

Local data goes in ignored `deployment/local/`, separate from the configured
course database and `deployment/auth/`. Startup runs the repeatable migration
and initializes the local deletion ledger once. Keep this directory to test
restoration across restarts; a new signing key invalidates old bearer tokens but
does not change conversation ownership. Missing/corrupt deletion ledgers beside
an existing local database fail closed. One launcher may use a data directory
at a time; the lock is released on exit.

`--save-dialogue` explicitly enables a **local-test-only one-hour retention
policy**. Also select the optional saving checkbox in the page before sending
a turn. Research consent remains independent. Without this flag saving is off,
and ordinary authenticated tutoring remains available. No manual `init-ledger`
command is needed for this launcher. Asking the tutor still uses your configured
model endpoint; a model availability error is separate from authentication.

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
Identity and assignment permissions are enforced by the backend. See
[the server contract](../docs/authentication.md) and run
`node frontend/tests/auth-client.test.cjs` for hermetic credential wiring checks.

## Optional saved dialogue

`conversation-client.js` supplies an authenticated Session for both API surfaces.
`api-client.js` exports `createConversationSession(exerciseId, onChange)`. The three
demos mount the same saving/history controls. The preview dev-client incorporates
the UI branch's layout and theme, with these controls inside Conversation Feed.
The server config response supplies the VERIFIED namespace and
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

Hermetic checks: `node --test frontend/tests/*.test.cjs` (28 passed). These exercise refresh,
new attempts, lost-response retries, pagination, unavailable/deleted history,
identity changes and credential headers, plus parse every demo inline script.

### Live replies and unavailable history

Saved turns deliver an optional `live_signals` object for the existing Glass Box.
These bounded, screened summaries are transient: they are not written to dialogue
storage or browser storage, and are absent from restored history and retry replay.
Restoring an attempt displays saved replies without inventing historical signals.
A failed history-network request after a completed turn still supplies its live
reply to the caller for display; refreshing replaces that transient display with
the server's authoritative messages.

An unavailable attempt clears the stale pointer and rechecks membership. If the
current assignment is still authorized, New attempt and turning saving off remain
usable. Recovery does not create an attempt automatically or extend its retention.
Expired local-demo attempts remain unavailable under the one-hour test policy.

### UI integration preview

`codex/ui-conversation-preview` starts from bounded-restoration `3a414d6` and ports
presentation from UI `0bd2def`: SVG logo, responsive columns, theme, Markdown feed
and widget typography. It does not import the UI branch's CC-B1 backend ancestry
or its unauthenticated POSTs. Current typed questions reach the backend, using
the legacy `who/text` contract when saving is off. Run results use the actual
pack-agnostic envelope; failed execution does not trigger a tutor call.
Glass Box summaries wrap instead of being silently truncated.

Run Result presents printed program output and a short execution status, with
exercise-check details available on demand. It does not display the JSON API
envelope; the complete response remains in RAM as authorized tutor context.
Execution success and exercise-check success are distinct, and output is literal
text so printed HTML is never executed. Empty output suggests using `print(...)`.

The dev-client uses a compact, viewport-sized desktop workspace at widths >=900px
and heights >=640px. Code and conversation scroll inside their own panels; the
question input sits beside the conversation rather than below the editor.
Controls use 34px heights (32px for conversation actions) and 8–16px gaps.
Optional saving stays visible, with human-readable creation-based retention;
refresh/older/delete actions are in a native More disclosure. Connection settings
are collapsed by default; Glass Box and run-check feedback start expanded and can
be collapsed manually. Run code sits in the Code Editor header. On narrow screens the conversation and
composer come first. Other demos retain the original shared-control presentation.

Markdown uses pinned marked 18.0.14 and DOMPurify 3.4.16 from jsDelivr, with
sanitization and safe external links. If either library is unavailable, model text
is escaped as plain text. There is no frontend build/install step.

The same `python -m app.local_dev --save-dialogue` command applies on this branch.
The initial inspected machine had existing servers on 8000/5173 and 8001/5174;
the separate preview was launched with unused ports and a separate local directory:

```powershell
python -m app.local_dev --save-dialogue --api-port 8002 --frontend-port 5175 --data-dir ..\deployment\local\ui-preview
```

Open the printed `http://127.0.0.1:5175/dev-client.html` for normal peer tutoring.
`?stance=control` provides a fixed support response without model calls for an
offline wiring check; it is not a peer-model demonstration. Stance remains fixed
for the page session, as in the existing enrollment-URL contract. Do not use the
synthetic local preview for actual student data. Ports and data directory affect
which namespace/attempt pointer is restored; preserve the directory for restart
checks and do not expect a different directory to contain the old history.
