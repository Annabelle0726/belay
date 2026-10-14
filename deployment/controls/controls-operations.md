# Shared controls: development and operator guide

Status: Stage B unsaved Ask is implemented and opt-in: original-principal live
reauthorization, owned temporary data, authenticated HTTP jobs, real worker adapter
and browser recovery. See `controls-stage-b-summary.md` for offline acceptance.
Saved-conversation integration remains Stage C. Tests do not enable a production
class rollout; operator policy, identity hosting and retention remain prerequisites.

## Policy and storage

`controls-policy.example.json` uses synthetic allowances and synthetic prices.
An operator must approve limits, currency, model/gateway bounds and retention
before production use. Model prices are integer currency microunits per token;
configure a conservative bound covering every tier and any cache premiums.
One microunit is one millionth of the stated currency. Missing provider usage
retains the full reservation. Token estimates and provider output parameters
are not a guarantee of the provider's invoice.

Limits apply simultaneously to deployment/institution/class/learner. `null`
is unlimited; zero is zero allowance. Periods are fixed UTC intervals from the
Unix epoch. Unresolved holds carry into future periods until reconciled. Actual
usage is charged to the reservation period. Currency or period changes are
rejected by ordinary policy updates: they need an audited migration.

All processes must use the same database and stable deployment scope. PostgreSQL
is the production coordinator; SQLite supports local development, not multi-host
proof. Current storage schema is additive `control_*` tables, initialized by the
operator command below. It does not alter learner/research tables. `init` is
idempotent for identical policy and does not silently replace an existing policy.
Back up before schema changes; API workers never auto-upgrade table layouts.
Existing coordinators from the pre-deadline implementation require the explicit
`upgrade-schema` command before using this worker version. It adds a nullable
`deadline` column and the temporary execution-data tables without changing accounting. Legacy active jobs have
no reliable deadline and become `unknown` on inspection/dispatch; investigate
them rather than replaying them. Queued jobs receive a deadline when claimed.

## Operator commands

From `../../backend`, use the installed project Python. Set `CONTROLS_DATABASE_URL`
to the intended coordinator using your normal secret injection. It is mandatory;
there is no fallback to the learner database or an in-memory budget. Example
commands (no credentials printed):

```text
python -m app.controls.cli init --policy ../deployment/controls/controls-policy.example.json
python -m app.controls.cli upgrade-schema
python -m app.controls.cli summary
python -m app.controls.cli unresolved
python -m app.controls.cli update-policy --policy approved-policy.json
```

The CLI is an operator surface protected by local execution and database
credentials. There is no student HTTP route for institution usage. Restrict the
database role and access to the shell accordingly. The summary reports queue
depth/bytes/oldest wait, job states, active/unknown slots, usage, rejection reasons
and reconciliation count. During a database outage rejection logging emits only
a stable reason code; no operational database can record while it is unreachable.

Financial reconciliation and proof of termination are separate:

```text
python -m app.controls.cli settle-attempt --target ATTEMPT_ID --actual usage.json --evidence INCIDENT_HEX_ID
python -m app.controls.cli confirm-stopped --target OPERATION_ID --evidence INCIDENT_HEX_ID
python -m app.controls.cli acknowledge-overrun --target ATTEMPT_ID --evidence INCIDENT_HEX_ID
```

`usage.json` contains nonnegative integers `tokens`, `microunits`, `runs`,
`wall_ms`. Obtain authoritative evidence first. An evidence reference is 32–64
hexadecimal characters referring to the operator's incident record, not free
text. `confirm-stopped` releases concurrency and closes unknown/running jobs as
failed; it does not refund budget. Acknowledging an overrun preserves the actual
usage and overrun record. Normal budget limits still apply. Replaying a settled
attempt with different usage is refused. No command silently requeues uncertain
provider work; exactly-once external execution is not claimed.

## Execution limits and uncertain outcomes

`execution_seconds` bounds a job from dispatch, independently of queue waiting
and the renewable heartbeat lease. The deadline is snapshotted at claim; a policy
update or heartbeat cannot extend it. At expiry the worker cannot publish or
start another external attempt. The next status/dispatch/operator inspection
persists `unknown`; expiration is lazy and there is no new background reaper.
Liability remains.
This fences work; it does **not** kill a provider request already in progress.
Use provider/runner termination evidence before releasing a concurrency slot.

A failed worker with an active/unknown external slot remains `unknown` with
`execution_unknown`, including during backend cancellation. Repeated submission
of the same operation returns that job and never automatically executes it again.
An answer received without usage may complete with its budget hold still unknown;
response uncertainty and financial uncertainty are separate. Completion requires
a nonempty opaque result reference. The actual Ask adapter additionally validates
owned, usable, unexpired output and atomically publishes it with completion in
the same coordinator transaction.

Content-free operation tombstones, attempts and reconciliation records are kept
indefinitely in this development slice to preserve replay protection and audit.
Production retention/archival and bounded rejection-log retention need an approved
policy and follow-up implementation before rollout. The ledger never stores
prompts, code, response text or bearer tokens. Separate encrypted `control_data`
rows temporarily hold operational input/results under the rules below; they are
never research/export rows.

## Reproducible coordinator demonstration

Use an isolated, disposable PostgreSQL database. `CONTROL_TEST_DATABASE_URL`
is test-only: the tests recreate `control_*` tables there. Do not point it at
an application or production coordinator. Set application `DATABASE_URL` to an
isolated test store too: the existing suite recreates learner-store tables.

```text
python -m pytest tests/test_controls_ledger.py tests/test_controls_admission.py -o addopts= -v
```

With `CONTROL_TEST_DATABASE_URL` set, two spawned processes with independent
connections verify a combined cap of 10 model slots and a 1,000-token budget
against competing 800-token requests. Deterministic tests show A0/B0/A1/B1 class
rotation while A has 50 queued jobs and B has 2. Without PostgreSQL configured,
the process tests explicitly skip. `tests/test_jobs_postgres.py` additionally
uses two independently authenticated HTTP processes and two real worker adapters
with an SDK stub: one stable logical request produces three accounted model
attempts and one published result. No paid endpoint is contacted.

## Integration checklist for Step 1/2

The adapter must derive scopes from verified identity and current grants, bind
the operation fingerprint to route/input/assignment version, and reauthorize
without persisting bearer tokens. Queue lifetime must be separate from an active
conversation turn: acquire the conversation revision/lease at dispatch. Check
deletion, expiry and ownership at dispatch and publication, and make conversation
publication atomic with its revision rules. Use an owned expiring input/result
store with deletion/revision publication rules. Stage B already supplies the
unsaved Ask adapter; Stage C must add these saved-conversation rules rather than
copying or inventing a second conversation system.

`CONTROLS_MODE=development_bypass` is the existing local workflow, explicitly
shown by both health routes. `enforced` blocks expensive HTTP requests without
trusted context; it is not an authentication replacement. A trusted operation
context always enforces accounting, even in a development test. Read-only
curriculum remains available to authenticated authorized callers when enforced
execution is unavailable.

## Incident recovery procedure

Assign an operator and an opaque incident reference. Do not ask the learner to
resubmit an uncertain Ask. Refresh/Check request status now performs protected GET
recovery of the same operation, without posting another billable request. A browser timeout or broken connection is not
evidence of provider termination, even if its local HTTP connection was aborted.

1. Inspect `summary` and `unresolved` using the selected coordinator credentials.
   Link attempt IDs and their operation ID in the incident record. Keep learner
   text, provider credentials and response bodies out of ledger evidence/logs.
   Snapshot inspection expires queued jobs and fences expired active jobs; it
   does not kill workers or refund external work.
2. Distinguish answer failure from execution/usage uncertainty. A received answer
   with missing usage can be completed while its hold remains unresolved. A lost
   provider response, lost worker or expired execution deadline must not be
   automatically requeued. The current branch has no student job/result lookup;
   a local frontend error is not an operational recovery API.
3. Obtain authoritative provider/runner completion or termination evidence and
   usage for each external attempt. Current ledger IDs do not guarantee a
   provider-side request ID; correlate securely with provider records. If records
   cannot establish usage/termination, leave the corresponding hold/slot intact
   and escalate to the deployment owner. Never invent zero usage. A timeout,
   worker heartbeat loss or elapsed billing period alone is insufficient.
4. Settle each attempt with `settle-attempt` using authoritative totals and the
   incident reference. Include all attempts, even if no answer reached the learner.
   The command rejects conflicting re-settlement. A late normal settlement of
   the same amount is harmless; a different amount is refused. Financial
   settlement alone does not release an uncertain concurrency slot.
5. Only after all external work for an operation has stopped, use `confirm-stopped`
   for that operation. It records the operator's assertion and releases slots;
   it does not terminate external work, refund holds or publish a missing answer.
   Fencing prevents the old worker from starting another controlled attempt or
   publishing. Investigate any attempt still reserved/unknown separately.
6. Verify `summary`/`unresolved` again and record evidence and remaining liabilities.
   Reusing the original operation ID returns its tombstone and does not rerun it.
   A deliberately new request is appropriate only after the prior operation is
   resolved and current authorization/funding permit it. No automated retry of
   unknown work is allowed. Policy changes for service continuity need explicit
   owner approval and a new policy version; they are not a refund.

HTTP errors from both tutor surfaces use content-free reason codes. `Retry-After`
survives route exception handling and is exposed to cross-origin clients. Generic
tutor exceptions return `execution_unknown`, without raw provider diagnostics.
This improves error wiring; it does not install authenticated admission or turn
the current synchronous endpoint into a recoverable job API.


## Stage B opt-in and operational retention

These are operator instructions, not actions performed by this implementation.
Before enabling, initialize a fresh isolated coordinator with an approved policy,
or run `upgrade-schema` for an existing coordinator. Use PostgreSQL across hosts.
Configure the same stable `CONTROLS_DEPLOYMENT_ID`, `CONTROLS_DATABASE_URL` and
protected `CONTROLS_DATA_KEY_FILE` on all API/worker processes. The key file holds
a Fernet key generated with `cryptography.fernet.Fernet.generate_key()`, readable
only by the service account. Do not commit/log keys or tokens. Keep the key stable
through active/data retention periods; rotation needs coordinated drain/migration.
Set `CONTROLS_MODE=enforced` and `CONTROLS_JOBS_ENABLED=true` only after setup.
No schema initialization or provider worker is started by an HTTP request.

Supervise `python -m app.controls.jobs_worker`; `--once` claims at most one job.
The worker uses the same operator authorization file as HTTP, re-read before
execution, external attempts and publication. It never stores bearer tokens or
accepts another principal as a substitute for the original subject. The actual
provider/runner attempts retain existing reserve/settle/unknown behavior.

Input expires at admission + queue_wait_seconds + execution_seconds, independently
of a later policy change. Results expire at staging + result_seconds (local demo
300 seconds, range 1–3600). Pending output must still be valid at atomic publication.
Terminal input/pending content is deleted on cleanup; unknown accounting is retained.
Schedule `python -m app.controls.cli cleanup-content` at least every minute even
when no worker or HTTP traffic is present. Expired content is inaccessible before
physical cleanup. Exclude `control_data` from long-lived snapshots/research exports;
content-free bindings/jobs remain dedup/authorization tombstones. Production
retention/archival for tombstones and rejection logs remains separate follow-up.

Both HTTP edges use the same normalized unsaved Ask schema:

- POST `/api/sol/jobs` or `/quad/v1/jobs`: `request_id` (16–128 opaque-safe chars),
  `exercise_id`, authorized `exercise_version`, `participant_id` and Sol turn fields.
  Client claims never create authority; server derives scope from R1 identity.
- GET `.../config`: authorized assignment versions, recovery scope, poll interval,
  retention and disclosure. GET `.../by-request/{request_id}` or `.../{job_id}`:
  original-principal protected state/result. Poll no faster than poll_seconds;
  respect Retry-After. Results are no-store and become `result_expired` after TTL.
- Same ID/input returns the existing task; changed input conflicts. Unknown jobs
  are never auto-claimed/retried. Clear terminal failures only after inspection;
  financial reconciliation and proof of termination remain separate commands.

The widget/dev Ask/client use this contract and preserve only a scoped opaque
pointer in browser storage. An unrendered/unknown result keeps that pointer pending.
No credentials, prompts or answers enter browser recovery storage. A fresh deliberate
Ask is possible after a displayed completed result or known terminal outcome. Clearing
storage loses the pointer and does not stop backend work. No learner cancel UI exists.
`/api/run` remains separate and fails closed without trusted operation context in
enforced mode; Stage B is the unsaved Ask slice, not queued runner integration.

Operational storage rejects PII even in source (stricter than source execution).
An enabled distress short circuit retains only content-free support routing; its
institution-configured response is rendered live at result lookup. No distressing
utterance, contact configuration, category or token is retained. The core detector,
support routing policy, research consent and R2 saved-dialogue strategy are unchanged.


## Explicit continuity for an unresolved unsaved request

An owner-approved temporary capacity change may keep an unresolved operation and
its execution/financial reservations intact while permitting a separate new Ask.
Use a new policy version; never mark the old operation stopped without evidence.
This is an exception for deliberate new work, not a retry of uncertain work.

The default `CONTROLS_OPERATOR_CONTINUATIONS` is empty. An operator may set it to
JSON with `policy_version` and `request_ids` only after approving the continuity
policy. The authenticated unsaved jobs config exposes only matching unknown IDs
owned by that original principal, with a current valid grant. The approval must
match the active policy version, and every active-job/model-call scope must have
capacity of at least two. Wrong policy, foreign ownership, revoked grant,
malformed approval, or an unlisted ID cannot enable continuation.

Refresh only checks the old request and offers Ask Sol. On the next deliberate
Ask/Run, the client rechecks it; only an approved unknown is archived under the
same recovery scope with an `:unresolved:<request_id>` suffix before a fresh
request ID is written and submitted. Storage failure prevents submission. The
old backend job, slots and budget hold are never changed. A successful/terminal
old result follows ordinary recovery instead. A new unknown is not automatically
approved by the older grant. Existing authenticated status lookup remains
available for the retained earlier request.

To revoke this allowance, remove the operator approval (or change policy version)
and restart the runtime. Restore concurrency to one using a new policy version
only when it will not block legitimate outstanding work. Do not reset usage,
re-prepare the installation, or manufacture a zero-cost settlement.
