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

## R3 — regression verification and local reproduction boundaries

R2 commit: `e55f48d`.
Goal: complete regression checks and document an honest retest without changing
the existing service/database. Files: `backend/tests/test_controls_worker.py`,
this summary. The full suite exposed an old assertion expecting an unbound Run
context. It now explicitly disables jobs and expects jobs_disabled for Run,
retaining anonymous/forged-body rejection and the old model-route expectations.
This regression plus the new Run tests: 16 passed, 0 failed, 0 skipped.
The full-suite run (before the corrected assertion) finished with **749 passed,
3 failed, 17 skipped** in 251.36 seconds. Failure triage:

- controls_worker Run assertion: corrected as above and all 16 relevant tests
  reran successfully.
- local_dev saving-on/non-controlled launcher: HTTP timeout at its 5-second test
  deadline; isolated rerun passed without code changes. This is not evidence of
  an app fix for every possible timeout.
- test_deploy's embed-page assertion: still fails on rerun because it requires
  `/quad/v1/turn` literally inside embed-demo.html, which already uses controlled
  jobs. The HTML and this test are byte-identical to starting commit 4231e39, as
  are the launcher files. This is existing test/contract drift outside the Run
  repair; neither the embed page nor this test was changed to hide that failure.

Full Ruff check/format and mypy pass after the test assertion change (158 formatted
files, 151 checked sources). Full frontend: **81 passed, 0 failed, 0 skipped**.
PostgreSQL checks were skipped without isolated database settings; no PostgreSQL
claim is made. The full backend suite was not repeated after the isolated fixes;
it is NOT reported as fully green. The final combined Run/identity/budget/job/
recovery/CORS regression set passed **57 tests, 0 failed, 0 skipped** in 13.98s.

Read-only live recheck: health reports datascience/openai_compatible/sql/
development_bypass; served dev-client.js, ask-jobs.js and request-lifecycle.js
match checkout byte-for-byte. The old browser tab's loaded version/history is
unverified. The pre-existing untracked integration review is untouched.
The confirmed config rejection blocks the unsaved automatic-feedback path before
its POST. Configuration GETs can also come from startup recovery, so the GET alone
does not prove the historical Run succeeded. If optional saving was on, the
current non-controlled saved route is separate; it was not exercised with real
models. No actual old job state was inferred from the screenshot/config response.
Root/backend qimvp.db, authorization rules, deletion ledger and backend .env
match the prior curriculum-repair manifest. The application demo.sqlite3 differs
from that PRIOR repair manifest and has last-write time 10:42:38, before the
final regression/check commits. That older manifest is not a start-of-this-task
snapshot; do not attribute that difference to this repair or claim a current-task
before/after hash proof. No command in this repair provisions the existing DB.

### Retest the existing preview without replaying an unknown request

Frontend: http://127.0.0.1:5175/dev-client.html
API: http://127.0.0.1:8002

1. Hard-refresh to load the new static client; do not clear storage. Inspect only
   status and response error codes, never copy Authorization. Config still returns
   503 jobs_disabled. There should be no false new-task-running claim.
2. For a deliberate NEW code run, click Run code once. Inspect /api/run separately:
   HTTP 200 plus ok=true and actual stdout/check details prove code execution.
   A runner failure should not dispatch tutoring. Do not replay an existing
   unknown tutor task for this check.
3. In this disabled configuration, successful Run should keep code output and
   say no new tutor feedback was submitted. No new POST /api/sol/jobs should occur.
   Old pending IDs stay in storage; no evidence is erased. This is the correct
   failure presentation, NOT proof that AI feedback is now available on 8002.

Actual feedback requires controls_mode=enforced, jobs_enabled, configured controls
DB/deployment/key with an existing initialized policy/schema, and a running worker
using the intended provider. These settings permit job/input/result and accounting
writes; a real provider could incur charges. Simply flipping the jobs flag is not
sufficient. No such settings were applied to 8002. The ordinary local_dev launcher
provisions data, so do NOT restart it against deployment/local/ui-preview under
the current no-initialization constraint.

### Optional synthetic demo — instructions only, not executed this round

This creates ONLY a fresh temporary test directory/database, uses the existing
datascience three-exercise pack, enables enforced controls and its worker, and
replaces all model factories with the local stub. It never reuses the existing
preview DB or calls a paid model. Choose unused ports; the launcher fails if busy.
Because automatic review blocked this round's demo launch, the following manual
browser procedure remains unverified, distinct from passing automated tests.

In a new PowerShell terminal:

```powershell
Set-Location C:\Projects\EduCloud-Ecosystem\belay\backend
$feedbackDemo = Join-Path $env:TEMP ('belay-run-feedback-demo-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $feedbackDemo) { throw 'Demo directory must be new' }
$env:TUTOR_PACK = 'datascience'
python -m app.local_dev --controlled-stub --api-port 8003 --frontend-port 5176 --data-dir $feedbackDemo --env-file (Join-Path $feedbackDemo 'unused.env')
```

Open http://127.0.0.1:5176/dev-client.html (API http://127.0.0.1:8003). Keep saving
off for the minimal Run demonstration. Choose Grouped summaries, enter synthetic
code `print("isolated code output")` followed by `result = {}`, click Run code once.
Expected: code output/checks, one feedback POST, queued/running/completed GETs,
and a nonempty `Local model stub` tutor bubble without manually clicking Ask Sol.
Refresh to recover the same logical task; never manually replay unknown tasks.
The temporary demo uses a synthetic local policy, not institutional retention
approval. Ctrl+C stops only that demo's two listeners. Do not commit its DB,
keys, grants, logs or tokens. Existing 8002/5175 should remain running untouched.
