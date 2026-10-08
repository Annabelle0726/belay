# Shared controls: development and operator guide

Status: ledger, admission service, execution hooks and worker adapter are
implemented. Authenticated HTTP jobs and real conversation integration are **not
available on this main-based branch**. Do not enable a production class rollout
on the strength of the coordinator tests alone. See `controls-implementation.md`.

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
Back up before future schema changes; this version does not auto-upgrade old
experimental table layouts.

## Operator commands

From `../../backend`, use the installed project Python. Set `CONTROLS_DATABASE_URL`
to the intended coordinator using your normal secret injection. It is mandatory;
there is no fallback to the learner database or an in-memory budget. Example
commands (no credentials printed):

```text
python -m app.controls.cli init --policy ../docs/controls-policy.example.json
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

Content-free operation tombstones, attempts and reconciliation records are kept
indefinitely in this development slice to preserve replay protection and audit.
Production retention/archival and bounded rejection-log retention need an approved
policy and follow-up implementation before rollout. The ledger never stores
prompts, code, response text or bearer tokens. Payload/result references require
a separately authorized TTL store; this branch does not create that store.

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
the two process tests explicitly skip. These are coordinator workers, not two
fully authenticated API servers. CI runs them in its ephemeral PostgreSQL job.

## Integration checklist for Step 1/2

The adapter must derive scopes from verified identity and current grants, bind
the operation fingerprint to route/input/assignment version, and reauthorize
without persisting bearer tokens. Queue lifetime must be separate from an active
conversation turn: acquire the conversation revision/lease at dispatch. Check
deletion, expiry and ownership at dispatch and publication, and make conversation
publication atomic with its revision rules. Use an owned expiring input/result
store with cancellation/deletion cleanup. The worker's adapter is intentionally
an interface until these contracts are available on the base.

`CONTROLS_MODE=development_bypass` is the existing local workflow, explicitly
shown by both health routes. `enforced` blocks expensive HTTP requests without
trusted context; it is not an authentication replacement. A trusted operation
context always enforces accounting, even in a development test. Read-only
curriculum remains available when enforced execution is unavailable.
