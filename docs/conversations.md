# Bounded conversation restoration

Implementation branch: `feature/bounded-conversation-restoration`, baseline
`6124598`, inheriting authentication at `8868234`. Authentication is an unmerged
dependency; no B1–B4 or UI-refactor branch is merged here.

For a standalone local demo, stop the separate uvicorn/http.server processes and
run `python -m app.local_dev --save-dialogue` from `backend`. Open the printed
`http://127.0.0.1:5173/dev-client.html` URL and select optional saving. The launcher
configures browser credentials, grants, migration and a provisional local ledger
in an independent ignored data directory. See [frontend instructions](../frontend/README.md).
It is an explicitly selected synthetic local host, not institution identity setup.

## Step 1 — separate storage purposes

HTTP learner state (concepts, goals, reflections and overlay) now uses the scoped
course store regardless of research participation. Participant initialization
creates a missing pseudonymous FK row with research consent false and never
changes an existing consent decision. Research events retain consent-based
durable/ephemeral routing. Direct legacy ConsentRouter users keep their original
store interface; HTTP ScopedStore composes course state and research events.

Saved dialogue will use dedicated tables and its own policy/learner preference;
the research `consent` field never grants dialogue saving. Saving remains disabled
until an operator explicitly configures approved retention and backup/deletion
rules. Ordinary tutoring remains available while saving is disabled.

CC-R1's inherited usage-field and analysis-reader findings remain open; this
milestone does not claim that inherited trace analysis is repaired.

## Step 2 — ownership and migration

A saved attempt has a server-generated ID and belongs to the verified institution,
class and learner namespace plus the granted exercise and deployed version.
Each attempt has an independent ordered revision. All storage operations use the
same indistinguishable 404 for inaccessible, expired or nonexistent attempts.
Old research events are never imported as messages. Create retries use an opaque
request ID and return the same attempt; creation quotas are serialized per owner
and assignment. Retention is fixed from creation rather than extended by activity.

With workers stopped, run `python -m app.conversations.migration` from `backend`
against the configured DATABASE_URL. Migration v1 adds dedicated conversation,
message, turn, quota-lock and schema-version tables; reruns verify the schema and
preserve existing data. It supports SQLite and PostgreSQL dialect upserts.
The application fails closed on an absent/incompatible dialogue schema.
Saving remains disabled by default. No guessed ownership or legacy backfill exists.

Step validation: seven hermetic SQLite migration/ownership/retry/failure tests.
PostgreSQL validation and the public API integration follow in later steps.

## Step 3 — authorized persistence and restoration

Both `/api/conversations` and `/quad/v1/conversations` expose the same protected
API: config, create/list attempts, metadata, messages, delete and `/{id}/turns`.
Create takes granted exercise/version, an opaque request_id and explicit `save:true`;
`save:false` needs no saving policy and does not create a record. Turn takes
request_id, expected_revision, the NEW learner message, and optional source,
mode/stance, read-only result and bounded overlay. Invented `recent` history and
unknown fields are rejected. Source and grading context are not persisted.
Membership/credential verification runs again after the tutor returns.

Only `message` and `check_question` from the final existing run_turn output are
saved. Planner/reasoner drafts, self-evaluation, hidden reasoning and components
are excluded. Pending learner messages have pending/failed status, without a
fabricated assistant reply. A short transaction reserves a single pending lease;
no database transaction spans inference. A completed duplicate returns the stored
response without another model call; changed input or overlapping/stale requests
return 409. A failed/crashed lease needs refresh and a NEW request ID, not automatic
model re-execution. Tutor state/research side effects are not an exactly-once
transaction with inference. Credentials and membership remain required on retries.

PII is rejected at intake using the existing boundary; released output is screened
again before saving. Existing distress vocabulary also screens saved content even
when distress routing is disabled. Sensitive exchanges store only the neutral
`[This exchange was not saved.]` placeholder for each side, with no category.
An authorized live support response can still be displayed, but is never saved;
a later retry/restoration returns the placeholder. Saving never writes research
consent, dialogue events, trace exports or grades. Changing governance/retention
policy must rotate policy_id, making prior-policy attempts unavailable.

Step validation: 25 storage and both-edge HTTP tests, including concurrent turn
reservation, plus the existing 167 auth-isolation tests (192 total).

## Step 4 — independent bounds

All numbers below are provisional LOCAL bounds, not approved course retention or
shared traffic/budget limits. Environment names are `DIALOGUE_` plus each uppercase
policy field (e.g. DIALOGUE_MAX_MESSAGE_BYTES). Invalid combinations fail closed.

| Bound | Default | Overflow |
|---|---:|---|
| Raw request body | 65,536 bytes | 413 before JSON parsing, including streamed/chunked bodies |
| New message / released saved message | 8,192 UTF-8 bytes | 413; failed reservation has no assistant message |
| Retained messages / attempt | 200 | 409; explicitly start another attempt |
| Retained text + serialized retry responses / attempt | 524,288 bytes | 409 before reservation |
| Active attempts / owner + assignment/version | 5 | 409; delete an attempt first |
| History page | 40 messages and 65,536 serialized JSON bytes | Scoped cursor for another page |
| Restored recent window | 16,384 conservative token units | Keep newest complete exchanges, ordered |
| Reserved response / model call | 1,024 tokens | Cap adapter max_tokens |
| Full model input + framing + response reservation | 32,768 units | 413 before provider request |
| Pending turn lease | 120 seconds | Old lease cannot complete; refresh and use new request ID |

Token accounting conservatively counts UTF-8 bytes, not a model-specific tokenizer,
plus 256 units for model message framing. Window selection subtracts response
reservation and retains the new learner message plus whole recent completed pairs.
A message that cannot fit alone is rejected. Actual planner/reasoner/self-evaluator
prompts are independently checked before EVERY provider call. Configure these
bounds for the deployed model's actual window. Anthropic extended thinking must be
disabled for saved dialogue because its adapter may increase the generation cap.
No saved history is removed when only the inference window is shortened.

Tests measured the worst JSON control-character expansion: one 8,192-byte message
can expand to 49,152 bytes before metadata, which fits the 65,536-byte page cap.
Storage reservations include a worst-case released response and its JSON retry
copy. The byte bound covers retained payloads, not physical database/index overhead.
Scoped cursors cannot be reused on another attempt. Page bytes include metadata,
status and cursor, not only text. Exact-limit tests cover byte/message counts,
creation quotas, input caps, recent pairs and the actual provider reservation.

Step validation: 31 conversation tests; Ruff and conversation/config mypy pass.

## Step 5 — retention, deletion and recovery

Durable saving is OFF unless DIALOGUE_ENABLED is explicitly true AND the operator
provides DIALOGUE_POLICY_ID, DIALOGUE_RETENTION_SECONDS (no production default),
DIALOGUE_BACKUP_MAX_AGE_SECONDS (no default) and DIALOGUE_DELETION_LEDGER_FILE.
Saving is optional per attempt; research consent is unrelated. Every attempt has
an immutable creation-based expiry. Withdrawal, class removal and deployed-version
change block every read/resume/retry via current authorization immediately.

Deploy with workers stopped:

1. Configure the approved saving/retention/backup policy and limits.
2. Run `python -m app.conversations.migration` from backend.
3. Run `python -m app.conversations.maintenance init-ledger` ONCE for a new deployment.
4. Start workers; config and saving fail closed without the schema and intact ledger.
5. Schedule `python -m app.conversations.maintenance cleanup` externally at an
   institution-approved interval. This implementation adds no queue or scheduler.

### CLI configuration and local PowerShell example

`python -m app.conversations.maintenance` does NOT automatically read `.env`.
Export the policy variables in the same terminal before running the command.
`uvicorn --env-file .env` loads settings only into that uvicorn process, not into
other Python commands or the browser. `init-ledger` requires all four policy fields
even when web saving is off. Missing or invalid fields now produce a CLI error
listing variable names/constraints, exit code 2, and no HTTP traceback. Initialization
does not require a database connection; a corrupt existing ledger is never reset.

For LOCAL TESTING ONLY, from `backend`:

```powershell
$env:BELAY_ENV = 'local'
$env:DIALOGUE_ENABLED = '0'
$env:DIALOGUE_POLICY_ID = 'local-test-only'
$env:DIALOGUE_RETENTION_SECONDS = '3600'
$env:DIALOGUE_BACKUP_MAX_AGE_SECONDS = '3600'
$env:DIALOGUE_DELETION_LEDGER_FILE = Join-Path $PWD 'data\local-deletions.jsonl'
python -m app.conversations.maintenance init-ledger
```

The one-hour values are disposable local examples, not approved production retention.
Initialization does not enable saving. To test saving, explicitly set
`$env:DIALOGUE_ENABLED = '1'`, run the migration and restart the backend from that
terminal. In production replace the examples with institution-approved policy values.
Keep the database DSN/cwd consistent between migration and backend startup. These
dialogue settings do not provide front-end authentication or an identity issuer.
Seven hermetic subprocess CLI tests cover missing/invalid policy, initialization
with saving off, reruns preserving deletion fences, corrupt ledgers and cleanup.

Delete clears messages and the retry response in the request transaction. Expiry
hides content immediately; physical purge waits for cleanup. Cleanup is repeatable.
Minimal SQL tombstones/quota metadata and content-free deletion IDs remain. A late
model completion cannot append to a deleted/expired attempt. Crash after ledger
append but before SQL commit still hides the content until cleanup succeeds.

The append-only deletion ledger is authoritative, independent of database backups,
and contains only conversation IDs. Never replace it with an older database backup
or silently initialize a missing ledger during recovery. It must live on a durable,
shared filesystem with atomic append/fsync semantics for all workers, restricted
operator ACLs and independent recovery/backup arrangements. Missing, malformed or
partial tails fail closed. Readers have no transcript cache. There is no automatic
ledger compaction: retain fences at least through retirement of every backup that
could contain the dialogue. Long-term metadata minimization needs institution
approval before deployment; SQL tombstones likewise carry no message content.

During recovery, keep workers stopped, retain the current ledger, and run
`python -m app.conversations.maintenance restore-check --backup-age-seconds N`.
The operator must supply the true backup age; backups older than the approved cap
are refused. This check purges restored deleted/expired content before serving.
Tests restore an actual SQLite backup and verify inaccessible history, blocked
create retries and physical removal. Backup destruction/retirement is an operator
obligation; the application does not manufacture approval or manage backups.

Step validation: 35 conversation tests, including expiry at its exact boundary,
delete during pending inference, repeatable cleanup, missing/corrupt ledger and
actual backup resurrection prevention; Ruff and conversation mypy pass.

## Step 1 refinement found during regression

Course run-attempt counts now have a dedicated content-free `course_attempts`
table keyed by the already scoped owner and assignment-version hashes. Atomic
upserts preserve counts across restart without research events. Migration creates
this additive table; no old event ownership is inferred and no historical counts
are guessed. SqlStore initialization remains compatible with existing deployments.
Memory stores use the same separate counter. Goals/concepts and run counts remain
available without research participation. Missing Quad consent fields preserve the
existing explicit research choice; explicit true/false still records that choice.
SQL parameter values are hidden in engine exception representations/logging.

SQLite restart and consent-preservation tests passed. Disposable PostgreSQL tests
verified existing records survive repeatable migration and concurrent creation and
turn reservation have one winner. This correction is committed independently of
the frontend restoration step.

## Step 5 refinement — cleanup while saving is disabled

Administrative cleanup and recovery checks continue to validate the configured
policy/schema/ledger while web saving is OFF. Disabling a feature must not stop
physical removal of previously saved expired content. The web APIs still refuse
saving/restoration in this mode. A boundary test verifies cleanup and its rerun;
the final full regression suite passes with this correction.

## Step 6 — frontend restoration and final validation

The shared conversation client implements optional saving, refresh restoration,
bounded older pages, explicit new attempts and deletion. It retains only scoped
attempt pointers/preferences in browser storage. New learner messages go to the
server-owned history API, with stable request IDs for a lost response. Identity
changes clear history and prevent submitting a previous learner's message.
Unavailable history clears its pointer; it is never silently replaced. Failed and
unfinished turns remain visible. The widget displays live unsaved support responses
while later restoration shows the privacy-safe placeholder. Demos retain all three
original CSS style blocks. See frontend/README.md for the host lifecycle event and
API-module Session factory.

Final results against the final backend implementation:

- Baseline: 541 backend passes, 7 existing skips.
- Full backend: **588 passed, 7 skipped**, including the disposable PostgreSQL
  migration/concurrency test. No identity or model service is contacted.
- PostgreSQL/SQLite configured-store scoping checks: **2 passed** against the
  temporary PostgreSQL container and temporary SQLite database.
- Frontend Node tests: **13 passed**; shared script syntax and all demo inline
  scripts validated. No browser/network service is needed for these tests.
- `python -m ruff check app tests evals`: passed.
- `python -m ruff format --check app tests evals`: 115 files formatted.
- `python -m mypy app tests evals`: passed, 114 files checked (existing untyped-test
  notes only). Existing Starlette/AnyIO deprecation warning is unchanged.
- Existing skips: one live model benchmark and six verifier-contract tests whose
  sibling checkout is absent. The PostgreSQL test was RUN, not counted as a skip.
- `git diff --check`: passed. No push, PR creation, merge or main/UI-branch edits.

Reproduce from backend using the local virtualenv, and set
TEST_DIALOGUE_POSTGRES_URL to a disposable PostgreSQL test DSN to run the isolated
schema check. The test never imports legacy events as dialogue and drops only its
own UUID schema. The temporary validation container is removed after validation.
Without that explicit test DSN, the PostgreSQL check is intentionally skipped.

Changed file groups:

- `backend/app/conversations/{models,migration,policy,repository,router,bounds,
  ledger,maintenance}.py` and package initializer: dialogue contract/storage,
  migrations, authorized APIs, bounds and lifecycle.
- `backend/app/{config,main}.py` and `integrations/quad/router.py`: configuration,
  mounts and explicit research-choice preservation.
- `backend/app/store/{consent,scoped,repository,models,db}.py`: independent course
  state/counts, consent routing and SQL parameter privacy.
- `backend/tests/test_conversation*.py`, `test_course_storage.py`,
  `test_auth_isolation.py`, `test_quad_sidecar.py`: hermetic regression evidence.
- `frontend/{conversation-client,api-client}.js`, three demos and two Node test
  files: minimal authenticated restoration integration.
- `docs/conversations.md`, PRIVACY.md, ARCHITECTURE.md, VALIDATION.md and
  frontend/README.md: purpose/ownership/API/deployment and actual validation.

### Remaining decisions and dependencies

Saving must stay disabled until the institution approves optional-saving notice,
creation-based retention duration, physical cleanup interval, backup lifetime,
deletion-fence metadata retention, operator ACLs and a supported shared ledger
filesystem/recovery procedure. This deployment configuration supplies ONE saving
policy: deployments serving multiple institutions/classes must have approval for
all served scopes, or use separately configured deployments for differing policies.
There is no automatic approval, backup manager, ledger compaction, queue or shared
traffic/token budget. Policy rotation invalidates old attempts; old payloads retain
their original expiry until cleanup, and may consume the active-attempt quota until
expiry. Plan rotation/cleanup operationally before changing policy IDs.

The inherited auth branch is still an unmerged dependency; actual EduCloud issuer,
roster and host lifecycle integration require agreement/testing. CC-R1's usage
metrics filter and legacy analysis-reader incompatibility remain explicitly open.
These results do not declare a production course deployment or upstream merge.

### Suggested pull request

Title: `Add bounded conversation restoration with independent retention rules`

Description:

Build on the unmerged authentication/class-isolation dependency to save and resume
server-owned dialogue per institution, class, learner, assignment version and
attempt. Keep course progress independent of research participation and make
conversation saving an independently optional, default-disabled policy.

Add repeatable SQLite/PostgreSQL migrations, transactional turn leases and
idempotent retries, bounded storage/pages/model context, creation-based expiry and
independent deletion fences that survive database backup restoration. Save only
released learner-facing answers; retain neutral placeholders for sensitive
exchanges. Add minimal authenticated frontend restoration/new-attempt/delete
controls without changing existing styles.

Validation: 588 backend tests passed, 7 existing tests skipped; 13 frontend tests
passed; PostgreSQL migration/concurrency and configured-store scoping passed;
Ruff check/format and mypy passed. Institution retention/backup/ledger approval and
actual EduCloud host integration remain required before enabling saving. Inherited
trace-metrics/analysis compatibility findings remain open. No queue or shared
budget system is included.

## Local startup follow-up — completed steps

1. **Maintenance diagnostics** (`6c13bbd`,
   `fix(conversations): explain missing maintenance policy configuration`).
   CLI validation now names missing/invalid policy variables, explains that the
   CLI does not automatically load `.env`, and exits cleanly instead of exposing
   a FastAPI traceback. Disabled web saving still permits operator maintenance.
   Seven hermetic CLI tests and the related lifecycle/bounds/HTTP tests passed.
2. **Authenticated loopback host**
   (`feat(dev): add authenticated loopback demo launcher`). `app.local_dev` starts
   both listeners, injects the host callback before existing demo scripts and
   supplies real five-minute RS256 credentials. It configures synthetic grants
   and separate ignored SQL/ledger files; the private key is never written.
   Default saving remains off; `--save-dialogue` explicitly selects a provisional
   local policy and still requires the learner's optional checkbox. Startup
   reserves ports and locks the data directory, preserves existing attempts and
   deletion fences, rotates signing keys and rejects missing/corrupt ledgers.
   No existing server process, UI layout or production authentication is changed.

Follow-up validation: full regression **607 passed, 8 skipped**, with one existing
Starlette/AnyIO deprecation warning. Skips: live model evaluation, unconfigured
disposable PostgreSQL DSN and six missing verifier-contract sibling tests.
The PostgreSQL check had passed for the previous milestone; it was not rerun for
these local-launcher/CLI changes. The final local-host suite separately passed
**14 tests**, including the additional restart/key-rotation/fence-preservation
case added after the full regression collected tests. Frontend: **13 passed**.
Ruff check/format and full mypy passed. Tests use temporary local files, real
ephemeral signing keys, loopback requests and offline control turns, with external
identity/model networking forbidden. Normal peer tutoring still needs the
configured model endpoint; this local issuer does not replace EduCloud integration.

## Preview correction — live output and missing-history recovery

The first successful saved-turn response now includes an optional `live_signals`
object with the existing learner-visible summaries: affect, intervention,
calibrated confidence, planner/self-check clauses, governance, concept memory,
self-evaluation flags and numeric stage timings. A bounded allowlist excludes raw
drafts, arbitrary components and model analysis. Existing PII/distress screening
suppresses sensitive summaries; sensitive exchanges receive no live signals.
This object is added AFTER database completion. It is never stored in messages,
turn replay data or research events. An idempotent replay returns the same released
response/revision without replaying these transient signals or running the model.
Restored history therefore has replies but no historical Glass Box data.

An unavailable saved attempt clears its browser pointer and rechecks current
membership. Successful reauthorization permits New attempt or disabling saving;
it does not silently replace history or extend retention. Authentication failures
still discard the previous namespace. Failed initialization can be retried after
host recovery. A history-network failure after successful completion no longer
hides the live reply, and changing attempts discards an obsolete late response.
No database migration or retention-policy change is needed for this correction.
