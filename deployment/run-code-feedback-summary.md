# Run code automatic tutor feedback repair — 2026-10-10

## R0 — current evidence and request boundaries

Goal: trace Run code, preserving requests and local data. Starting branch
`fix/dev-client-curriculum-startup` at `4231e39`; only the pre-existing untracked
controls review is present. Work branch: `fix/run-code-tutor-feedback`.
Files changed in R0: this summary. No local database or browser storage changed.

The original preview still runs as PID 31124, using the private non-provisioning
restart helper from the curriculum repair, on frontend 5175 / API 8002.
The served dev-client, task client and request lifecycle bytes match the checkout.
Live signed GET `/api/sol/jobs/config` returns 503 `jobs_disabled`; health/config
show datascience, development_bypass, optional saving enabled and controlled jobs
off. The configured application DB has no R3 control tables; its durable events
table is empty. This does NOT prove no code ran: no-consent traces can be ephemeral.
The current service was not restarted or reconfigured during this investigation.

Actual source chain: Run click awaits authenticated `/api/run`; if its result.ok
is true it calls `ask('run')`, carrying source and run result. Incomplete exercise
checks still qualify when code ran; a failed runner does not trigger feedback,
matching the UI branch's original behavior. The unsaved feedback path GETs task
config before generating/storing a request ID or POSTing. A live `jobs_disabled`
config therefore stops THIS new feedback before admission. There is no task to
poll for that failed attempt; an older pending request is a separate possibility.
No paid-model fallback should bypass this failure.

The shared request helper treats nearly every 503 as execution uncertainty,
including this explicit pre-execution configuration rejection. The Run handler
then shows Check request status and a potentially-running warning. Startup
recovery queries config even without a pending request, so the same wrong warning
can also appear before a Run. Old pending pointers do correctly prevent a new
feedback POST and must remain intact, even if a newer code run succeeds.

The accessible browser session has no existing dev-client tab; the user's Chrome
extension could not supply its tab/history. No user tab was reloaded or storage
cleared. Asked for the affected `/api/run` response and whether a task POST occurred.
Without that record, the historical Run's result and any older task's actual state
remain unverified; current source/config and isolation reproduction are evidence,
not a substitute for that missing request history.

Additional source boundary to verify: in enforced mode `/api/run` currently calls
`current()` without creating an operation context. Merely enabling task settings
would make synchronous code execution fail before the runner. The proposed repair
will reuse trusted identity/grant checks and existing runner accounting for that
synchronous route, without introducing queued code tasks or weakening budgets.
Verification/repair pending. No existing task was executed or replayed.

## R1 — trusted context for the existing synchronous runner

Goal: make a successful Run possible when controlled tutoring is enabled, without
adding code queue jobs. Files: `backend/app/main.py`,
`backend/app/controls/run_http.py`, `backend/tests/test_run_feedback.py`, this summary.

Cause reproduced: all three new signed HTTP tests failed with 503
`verified_execution_required` before repair. The Run route had no trusted operation
context in enforced mode. The context now uses the authenticated identity's scope,
a fresh synchronous operation ID and the original subject's live authorization
grant. Existing runner_call performs reservation/concurrency/settlement. Authority
is rechecked before execution and before returning/tracing results. Explicit
development bypass remains unchanged. No DDL, new queue or provider fallback.

Verification: 3 new tests pass, including real datascience sandbox stdout followed
by a stub tutor job, duplicate feedback POST producing one job/45 accounted tokens,
runner budget denial, forged learner denial, and revocation after execution
blocking result release even though another subject retains the same scope.
Related backend regression: 44 passed, 0 failed, 0 skipped. Ruff check/format on
app/tests and mypy app passed. An initial mypy failure (guard returning Identity
instead of None) was fixed with an explicit None-returning guard. Full backend and
full quality checks are in progress; PostgreSQL and live browser are unverified.

Remaining: frontend rejection classification and old-request attribution are
implemented but will be recorded/committed as R2. Current API 8002 still runs the
previous backend code and disabled jobs configuration. No service configuration,
existing database, request record, auth policy or credential was changed. R1's
commit ID will be recorded in the next entry after committing this step.
