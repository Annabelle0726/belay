# Bounded conversation restoration

Implementation branch: `feature/bounded-conversation-restoration`, baseline
`6124598`, inheriting authentication at `8868234`. Authentication is an unmerged
dependency; no B1–B4 or UI-refactor branch is merged here.

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
