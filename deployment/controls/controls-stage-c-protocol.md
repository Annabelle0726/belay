# Saved Ask through shared controls

## Configuration and storage contract

Saved Ask reuses R1 authorization, R2 dialogue and R3 admission/accounting. It
requires `DATABASE_URL` and `CONTROLS_DATABASE_URL` to select the same physical
SQL database, conservatively checked using their configured URLs (absolute paths
for SQLite). Configure matching PostgreSQL URLs, including connection options.
Both the R2 migration and controls `init`/`upgrade-schema` must be run explicitly.
There is no automatic schema creation, data relocation or legacy ownership import.
Separate database configurations return `saved_database_mismatch`; unsaved Stage B
continues independently. Cross-database publication is **not implemented** and
must not be described as atomic or enabled by removing this check.

The additive `control_conversations` table contains job ID, conversation ID,
expected revision and policy ID only. The existing grant binding identifies the
original submitting principal without a bearer token or raw subject. Temporary
encrypted `control_data` holds bounded input and released results. R2 messages
and turns remain the only saved conversation archive. No Glass Box analysis,
planner drafts or live signal summaries are persisted for saved jobs. Sensitive
saved exchanges contain the existing neutral placeholder; support frames are
rendered from current institutional configuration at result lookup.

The Stage B strict operational storage screen also applies. With distress routing
disabled, an input that cannot be safely queued is rejected; it is not secretly
retained or sent synchronously. This is an intentional queued-execution limitation.
No detector vocabulary, saving default, consent decision, policy ID or creation
retention duration is changed by this integration.

## State and transaction sequence

1. Signed HTTP submission resolves the live principal and R2 owner/assignment.
   A stable browser request ID, conversation, revision, route and immutable input
   determine an idempotent admission. Same ID/input returns its existing job;
   changed input conflicts. Input, grant, job and conversation link commit together.
   No student message is inserted while waiting in the queue.
2. A worker claims the existing fenced job, rechecks the original grant and the
   R2 policy/owner/deletion ledger/expiry/revision, and calls R2 `begin` under the
   coordinator connection. The R2 turn ID is the opaque job ID. Revision `r`
   becomes `r+1`; the normal R2 pending lease starts now. Completed history comes
   from R2, not client-supplied history. R2's context and provider bounds apply.
3. Database transactions end before inference. R3 checks the original grant and
   conversation/turn fence before execution and each external attempt. Internal
   JSON/model retries have their own accounting attempts, never new conversation
   turns. Worker heartbeat and immutable execution deadline remain independent
   from the R2 pending lease and queue timeout; the stricter expired boundary wins.
4. A released response is validated, screened and staged as an encrypted pending
   result. Publication rechecks live authorization and both fences. **One SQL
   transaction** writes the R2 assistant reply/revision `r+2`, owned result and
   `completed` job. No transaction spans inference. SQL rollback or process exit
   before commit leaves no assistant/result completion; no cross-database protocol
   is claimed. Completed reads also require the R2 completed receipt.
5. A lost response is recovered by protected GET of the same request. Browser
   storage contains only scoped opaque IDs/preferences. Unknown or missing jobs
   never automatically cause another POST. Pending pointers remain unresolved
   until a usable reply is handled or a definite terminal outcome is received.
   New attempts/identity changes fence obsolete UI callbacks.

R2 history-only APIs retain their contract. In enforced mode, the older
`/{cid}/turns` POST enters admission and returns 202; new clients use
`/{cid}/jobs`. There is no synchronous saved-turn bypass in enforced mode.
Both `/api/conversations` and `/quad/v1/conversations` offer:

- `GET /{cid}/jobs/config`
- `POST /{cid}/jobs` (NewTurn fields plus authorized exercise/version/participant)
- `GET /{cid}/jobs/by-request/{request_id}`

Existing protected Stage B status endpoints also check a saved job's R2 boundary.

## Failure, deletion and retention

Definite failed/cancelled jobs mark the existing R2 turn failed. Unknown jobs mark
it unknown; they never fabricate an assistant reply or become queueable. A staged
result followed by a worker crash is not automatically replayed or republished:
after lease loss the request stays unknown and needs operator investigation. A
completion committed before an acknowledgement loss is recovered without another
model call, dialogue append or settlement.

Deleting a conversation records the independent R2 deletion fence and erases
messages, turns and linked temporary input/results within its SQL transaction.
Queued/running workers cannot recreate it. Expiry denies all reads/publication,
bounds temporary rows by the conversation's creation expiry and erases content
through existing R2 maintenance and controls cleanup. Deletion/publication both
lock the same conversation row; PostgreSQL tests cover both winning orders.
Restoring a database must keep the independent deletion ledger and run R2's
restore-check before serving, as before. A DB backup does not restore authority.

Revocation stops future guarded work/publication/result access. It cannot
retroactively terminate an already transmitted provider request. Unknown usage
continues to hold its reservation; deletion, expiry, UI timeout or process exit
does not prove zero cost or refund it. Existing operator reconciliation and proof
of stopping remain separate actions.

Run both maintenance commands with the configured dialogue policy/ledger and
explicit database URLs. Keep temporary `control_data` out of long-lived backups
and exports even when sharing the dialogue database; a whole-database backup now
needs explicit exclusion/approved handling of that table. No backup job or actual
policy has been changed here. Production still requires institution-approved
retention, keys, cleanup/backup handling, budgets and operational supervision.

## Isolated local demo — no model service

Use a new private temporary directory and unused loopback ports. From `backend`
in PowerShell:

```powershell
$env:TUTOR_PACK = '_skeleton'
$savedAskDemo = Join-Path $env:TEMP 'belay-saved-ask-demo'
python -m app.local_dev --controlled-stub --save-dialogue --api-port 0 --frontend-port 0 --data-dir $savedAskDemo --env-file (Join-Path $savedAskDemo 'no.env')
```

The printed browser URL uses real five-minute signed synthetic credentials.
`--controlled-stub` explicitly provisions local controls in the same demo DB and
starts a worker whose model factory is a local stub, including secondary model
guards. No SDK/model networking is constructed. The normal launcher/provider
defaults are unchanged. Local provisional policy is not production approval.

1. Open the printed `dev-client.html`, leave saving off, and Ask: the Stage B reply
   appears. The code-run button is outside controlled Ask scope.
2. Check **Save conversation (optional)** and ask: one student/reply pair appears.
3. Reload: the same conversation restores. Disconnect after submission, then
   reconnect/reload or Refresh history: the same opaque request is queried, never
   silently resubmitted. Unknown outcomes show uncertainty and retain their pointer.
4. Use More → Delete saved attempt: history disappears. A late reply cannot restore
   it. Choose New conversation explicitly to start another saved attempt.
5. Ctrl+C stops this demo's listeners and synthetic worker. Do not reuse a live
   deployment directory or real student data for these checks.

Automated validation uses `python -m pytest -ra` from `backend` and
`node --test frontend/tests/*.test.cjs` from the root. Pytest creates a temporary
SQLite application DB unless an explicit isolated `DATABASE_URL` is supplied.
For disposable PostgreSQL, set `DATABASE_URL`, `CONTROL_TEST_DATABASE_URL` and
`TEST_DIALOGUE_POSTGRES_URL` to test databases only. The latter tests create/drop
their own schemas; older controls acceptance tests recreate their control tables.
Never point these variables at an application/deployment database. Run
`python -m ruff check .`, `python -m ruff format --check .`, and `python -m mypy`
from `backend`. See the summary for actual pass/skip counts and visual evidence.
