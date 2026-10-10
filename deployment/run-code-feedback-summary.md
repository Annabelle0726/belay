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

## R2 — distinguish non-submission from an unknown previous task

R1 commit: `b14d1c7`.
Goal: keep automatic Run feedback and honest recovery messages. Files:
`frontend/request-lifecycle.js`, `frontend/ask-jobs.js`, `frontend/dev-client.js`,
their three matching test files, this summary.

Explicit jobs_disabled/jobs_not_configured responses are known setup denials.
Configuration GET failures are tagged configuration/notSubmitted: that GET cannot
dispatch work, including on a lost response. This does not resolve or remove a
previous pending pointer. A definite rejection of a newly generated POST retains
a non-pending, not_submitted receipt, rather than polling a nonexistent task;
refresh skips that rejected receipt. Generic POST outages and unknown jobs still
keep the pending ID and prohibit automatic resubmission. Recovered replies/errors
are attributed to the previous tutor request, not the latest code run.

The UI keeps successful code output visible and explicitly says when no feedback
was submitted. Run still automatically submits event=run with source/result and
renders a valid completed reply when the service is configured; failed code runs
still do not trigger tutoring. No paid fallback, cancel button or data reset.

Verification: all frontend tests 81 passed, 0 failed, 0 skipped. Coverage includes
Run->one feedback POST->display, successful code with disabled feedback/no new
pointer or POST, prior unknown request unchanged across another deliberate Run,
config-network failure retaining an older ID, and rejected receipt recovery.
Full Ruff check/format passed (158 files); full mypy passed (151 source files).
Backend full suite is still running. PostgreSQL and a live browser Run remain
unverified in this round. Original historical /api/run status is still unavailable.

Service evidence remains PID 31124 listening on 127.0.0.1:8002 and :5175. Static
files now reflect these checkout edits when newly loaded; the existing browser
tab has not been reloaded. Its loaded frontend version is not asserted. The API
process has not reloaded the new backend context. Thus this is a verified code
repair, not a claim that the existing disabled service can now generate feedback.

An attempted isolated stub demo process launch was rejected by automatic approval
review with `blocked by policy` and no specific reason. It was not retried or
worked around; no demo listener was started by that action. Tests use isolated
test databases and stub providers. Existing application DBs were not initialized,
cleared or migrated. Remaining service/demo prerequisites and final counts follow
in R3. R2 commit ID will be recorded after committing this step.
