# CC-R3 follow-up implementation summaries

Baseline: `a48b7b1`, `feature/shared-traffic-budget-controls`, original checkout.
Product decision: no learner-initiated Ask cancellation control. Existing backend
cancellation, fencing and evidence-backed recovery remain in place. No deployment,
branch merge, or paid model call is part of these rounds.

## Round A1 — worker outcome and execution boundaries (2026-10-09)

- Require a nonempty opaque result reference for completion. This closes empty
  completion, but actual stored-result validation still belongs to the HTTP/TTL
  integration, which is not installed here.
- Keep failed/cancelled work `unknown` when an external slot is active/unknown or
  an attempt remains reserved. Do not requeue it or refund uncertain liability.
- Preserve delivery of a usable answer when only provider usage is missing.
- Snapshot an independent execution deadline at dispatch. Heartbeats and later
  policy updates cannot extend it; late workers cannot publish or start another
  attempt. This is fencing, not remote process termination.
- Add explicit, repeatable operator schema upgrade. Legacy active jobs without a
  deadline fail closed as unknown; queued jobs get a deadline at dispatch.

Validation: SQLite full backend regression: **432 passed, 9 skipped** before
adding the separate PostgreSQL legacy-upgrade case. Targeted controls tests:
**46 passed, 2 skipped** on SQLite; **48 passed** on disposable PostgreSQL before
that additional case. The added PostgreSQL legacy-upgrade check then passed
separately (**1 passed**). Ruff lint/format and
mypy passed (108 source files). Tests use synthetic adapters/providers and
temporary databases, including timeout/replay, missing usage, empty result, late
response, heartbeat deadline, migration and cancellation. The PostgreSQL run
includes the two independent-process budget/concurrency races.

Remaining dependency: Step 1 verified identity and live grant recheck, followed by
owned TTL input/result storage and HTTP/worker integration. No end-to-end Ask claim.

## Round A2 — reference Ask failure handling (2026-10-09)

Previous round commit: `3eecbb3`.

- Share a 90-second JSON transport deadline across widget, dev page and API
  client, including response-body reads. Never automatically retry a POST.
- Reject malformed/empty turn responses before display; tolerate absent optional
  telemetry while rejecting metadata that would break rendering.
- Distinguish explicit denial from ambiguous network/timeout/server failure;
  explain that server work may continue and do not advise a fresh submission.
- Block page-local repeated clicks and uncertain resubmission. Fence responses
  after context changes, including switching away and back. Preserve widget input
  and previous valid answers on failure, without adding empty/error tutor history.
- Keep run-and-Ask under one guard; a failed run never proceeds to Ask.
- Keep background recovery/cancellation; add no learner cancel control.

Validation: **23 Node tests passed**, including actual widget/dev page scripts in
a minimal DOM harness with mocked fetch, stalled bodies, malformed JSON and
deferred old responses. CI now runs all three frontend test files. No real browser
or authenticated HTTP acceptance is claimed.

Limitations: this gate has page lifetime only. Refresh, another tab/device and
server replay still require Stage B's stable operation ID and authenticated status
lookup. The API client exposes uncertainty but leaves UI locking to its host.
No credential, prompt, response or recovery token is persisted by these changes.

## Round A3 — HTTP errors and operator recovery (2026-10-09)

Previous round commit: `9729f42`.

- Preserve `Retry-After` through both tutor routes, the global handler and the
  standalone embedded Quad router; expose the header through CORS.
- Return a stable `execution_unknown` code for unexpected tutor failures instead
  of provider exception text. A generic server failure does not prove zero work.
- Document an evidence-based incident sequence: inspect, establish external
  completion/usage, reconcile each attempt, confirm stopped work separately, and
  verify remaining liabilities. Missing evidence keeps liability held; no timeout
  refund, automatic unknown-job retry or implicit provider termination is added.

Validation: full backend regression **438 passed, 10 skipped** on temporary
SQLite and **441 passed, 7 skipped** on disposable PostgreSQL, including all six
new HTTP cases, both independent-process races and the legacy schema upgrade.
SQLite additionally skips the three PostgreSQL-specific checks. Both runs skip
one opt-in live-model benchmark and six unavailable sibling verifier-contract
cases. Ruff lint/format passed; mypy passed (110 source files). HTTP tests replace
tutor/runner calls with stubs and exercise actual routes/CORS. They prove error
wiring, not trusted identity, admission, result storage or authenticated recovery.

## Round B0 — verify integration prerequisites (2026-10-09)

Previous round commit: `d02bdde`.

Inspected the actual Step 1 identity branch (`266c23e`) and Step 2 conversation
branch (`3a414d6`) without checkout, copying, merging or execution. Recorded the
smallest unsaved-Ask integration sequence and acceptance evidence in
`controls-http-integration-plan.md`.

Finding: Stage B can reuse Step 1's verified `Identity`/authorization contract,
but the current base has none of it. The inspected identity object also lacks an
original-subject-bound grant reference/live worker recheck. Trusted HTTP ownership
and token-free reauthorization must be resolved before wiring a real worker.
Owned TTL input/result storage and atomic result publication remain unimplemented.
Step 2's entire conversation branch is unnecessary for the first unsaved slice.

Status: **Stage A implemented and committed; Stage B/C/D not complete.** This
readiness round adds documentation only, not authentication or an end-to-end
capability claim. No user cancellation feature was added. Existing unrelated
workspace documentation/local setup changes remain outside these commits.
