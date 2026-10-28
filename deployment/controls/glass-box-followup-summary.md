# Glass Box quoted follow-up — 2026-10-13

Scope: Belay only. Branch `feature/shared-traffic-budget-controls`; the working tree
was clean at entry. Prior Glass Box/privacy work is preserved. No deployment,
real model call, local runtime configuration, budget or database modification.
Implementation is not yet committed.

## Step 1 — reference contract and server-owned resolution

Files: `backend/app/schemas.py`, `controls/data.py`, `controls/saved.py`,
`conversations/repository.py`, `conversations/router.py`, `main.py`, and
`tests/test_reply_followup.py` (all backend paths).

Added an ID-only `reply_to` contract. The server resolves the released answer,
checks the original principal/assignment or saved conversation owner, expiry and
status, and repeats checks before execution, further calls and publication.
Saved quotes stay in the same conversation/deletion scope. Missing/expired replies
return `reply_unavailable`; no replay or substitute reply. R2 turn response JSON
holds bounded quote metadata for history; no schema or retention changes.
Legacy unsaved synchronous Ask rejects references because it has no owned result
store. Controlled saved/unsaved Ask remains the normal UI path.

Verification: initial API regression failed with 422 before implementation; new
focused tests now pass (9). They cover duplicate admission, same learner/different
principal, missing/expired reference, revocation, saved history and cross-retention
rejection, ordinary questions/corrections and bounded long context. Two intermediate
assertion failures were corrected: revoked resources intentionally use 404, and
the saved-only fixture does not mount the unsaved route. Mypy: 161 files passed.
Remaining: PostgreSQL concurrency run and real model behavior not verified here.

## Step 2 — student interaction and explanation

Files: frontend dev-client HTML/JS, ask-jobs, control-messages,
conversation-client and related tests; backend agent context, reply_context,
reasoner, planner, orchestrator and glass_box.

Replaced Correction preparation with a removable quote above the existing input.
Click preserves draft/focuses input; no send. Empty quoted Ask does not submit.
Quotes appear beside their student message and survive saved history restoration;
client request ID and saved server task ID map to the same group. Historical
answers have the same follow-up entry. Latest Glass Box stays collapsed below its
answer. Markdown, silent loading and existing column layout remain intact.

Context separates the quoted answer (bounded to 6000 characters, with truncation
flag) from the new request's run. Original full code/run is not invented when it
was not retained. Planner/reasoner receive explicit follow-up guidance without new
model calls. Punctuation-only questions ask for clarification deterministically
after existing safety checks. Private diagnostics remain absent from student DTOs.

Verification: dev-client tests 45 passed; full frontend run before the final two
new tests: 107 passed. Safe Markdown, saved/unsaved recovery, late/unknown status,
long quotes, remove/draft and blank-submit behavior covered. No failed assertions
remain in these runs. Browser check and final complete regression pending below.

## Step 3 — offline preview and final verification

Fixture files: `frontend/tests/feedback-browser-fixture.js` and
`frontend/tests/build-feedback-fixture.cjs`. Generated HTML remains ignored.
The badge explicitly says Offline model stub preview. All API fetches are
intercepted with synthetic data; unmatched calls fail locally, never reach 8004.
This preview is not a real model, platform integration, or production acceptance.

Final evidence:

- Frontend full regression: **109 passed, 0 failed, 0 skipped**.
- Backend related API/worker/conversation regression: **74 passed, 0 failed**
  (includes all 9 new reference tests).
- Backend complete run: **849 passed, 1 failed, 18 skipped** out of 868.
  The failure was `test_local_dev.py::test_launcher_real_auth_course_and_optional_dialogue[False-True]`:
  a five-second HTTP timeout on the saved synchronous control turn. Exact-case
  rerun passed in 7.12 seconds total; cause not established, no timeout relaxed.
  The full run is therefore NOT represented as entirely green.
- Skips: PostgreSQL DSN-dependent tests (11), real LLM evaluation (1), unavailable
  sibling verifier-contract checkout (6). No real model effects or production
  load acceptance claimed.
- Ruff check and format check passed (162 files); mypy passed (161 source files).
- Real Chromium browser over the offline fixture: saved and unsaved Run,
  expand Glass Box, add/remove quote, preserve draft, submit ordinary quoted
  question, quote an older answer, and submit `?` all exercised. Old/new answer
  groups retained; only latest answer has one collapsed Glass Box. Console had
  no warnings/errors. Safe Markdown and code highlighting visibly retained.
- At 1440 x 1000, left/right top=64, bottom=984, width=696. The existing equal
  column layout is unchanged; the quote and chat remain within the right panel.
- Saved refresh and late-result cases are covered by automated JS/API tests;
  the standalone browser fixture resets its in-memory data on refresh and is
  NOT proof of server persistence across a real browser reload.

Preview: `http://127.0.0.1:5177/tests/fixtures/generated-feedback-preview.html`.
Run code, expand Glass Box, choose Ask Sol about this reply, then type a question.
The page explicitly says Offline model stub preview. Screenshot is local-only:
`deployment/local/glass-followup-browser/follow-up.png`.

Runtime: the existing real backend was not restarted. To apply the new API and
worker code, the operator must stop/start the existing runtime using the current
root `stop-belay.ps1` / `start-belay.ps1` scripts, then refresh the page. No prepare,
new budget, credentials copy or schema migration is required. Startup retains
normal queue behavior; this change does not replay unknown tasks.

Limits: no quote transfer across conversation/temporary retention scopes; an
expired temporary answer can stay visible in current RAM history but cannot be
resolved for a new server-side quote. R2 history retains dialogue and quote
metadata, not original source/run or private diagnostic snapshots. No new Glass
Box is fabricated on old saved-history restoration. Actual model interpretation
quality and full platform integration remain unverified. No commit/push made.


## Live recovery diagnosis and runtime activation - 2026-10-13

The reported Run code failure was traced to an unresolved prior Ask pointer.
Run succeeds and invokes Ask, but Ask recovers the pending operation before
admitting new feedback. The running API (started 17:49:09) had reply_to support
but lacked the later reconcile route added to jobs_http.py at 18:01:01.
Its config omitted missing_request_recovery. The reported request
`d0d1b36b-6b3c-4ade-b8f6-24c722db740d` returned job_unavailable (404).
Read-only inspection found 23 completed and 12 failed jobs, no active jobs;
latest admitted feedback was at 16:36:58 despite later runner activity.

Actions: verified the existing recovery changes with 18 frontend Ask tests and
4 backend missing-request recovery tests, all passing. Restarted through the
existing stop-belay.ps1 / start-belay.ps1 scripts using the same configuration.
The live API now advertises missing_request_recovery=1 and exposes reconcile.
Reconciled only the reported prior request through the authenticated endpoint:
HTTP 200, failed/request_not_admitted. This creates a non-admission tombstone;
it does not cancel work, replay a question, reserve budget, or call a model.

Verification used the actual JS served by 5177 against the real API on 8004,
with an isolated in-memory pending pointer for that reported request. The
network guard blocked all model-admission POSTs. Recovery returned
uncertain=false, notSubmitted=true and changed pending to false. This proves
the served recovery client and live backend agree; it does not inspect or
modify the user's open browser storage. The page needs a refresh to load the
current scripts and run recovery in its own storage scope.

No model call was submitted; latest model attempt remained unchanged. Existing
budget policy, USD 5.148223 cumulative cap, database and deployment were reused.
No prepare, migration, budget grant, commit or push. Actual model feedback after
a new user submission and the user's existing browser page remain unverified.

## 2026-10-14 - recovery 429 and provider authentication diagnosis

Reported request: c6ca4e00-a356-49b6-8694-90a092984122.
The live coordinator and read-only SQLite inspection agree: unknown /
execution_unknown, one unknown model attempt and one unknown model slot.
This is not an absent request. The retained model reservation is 16683
microunits, actual usage unknown. No historical exception type was retained,
so the cause of this specific old attempt cannot be established retroactively.

Two consecutive authenticated recovery checks reproduced HTTP 200 unknown,
then HTTP 429 poll_limited with Retry-After: 2. The browser is allowed to read
Retry-After through CORS. Existing retry logic already waits and does not
resubmit a model request. The 429 is not evidence of a model budget denial.

A non-inference GET /models to the configured DeepSeek endpoint, using the
launcher file credential source (backend/.env; no inherited key in this
inspection process), returned 401 authentication_error. No key was printed.
This proves the file credential currently fails authentication, not which
credential/error the earlier running process used.

Changes:
- Explicit provider 401/403 now releases the execution slot and ends the job
  as failed/provider_auth_failed. Unknown usage remains reserved; no assumed
  zero-cost refund. Timeouts, connection losses and 5xx remain conservative.
- Added content-free model-failure logs (operation/attempt/category/status,
  no exception text, keys, URLs or prompts).
- Poll throttling reports waiting on the existing record and honors Retry-After.
- Refresh recovery now labels an unresolved request as Check request status;
  confirmed authentication failure returns Ask Sol and preserves the draft.

Verification: 71 frontend tests passed; 30 focused backend tests passed,
including authentication rejection, uncertainty, recovery, and no replay.
Ruff check/format, git diff --check and targeted mypy (one source file) passed.
API/worker restarted through existing scripts only after installation-lock
release was confirmed. API is ready; updated frontend scripts are served.
The old job, unknown slot and budget reservation remain unchanged. Latest model
attempt is unchanged: no inference request was sent. No prepare, migration,
budget change, manual job closure, commit or push.

Remaining: correct the local DeepSeek credential, then validate authentication
without inference. Historical unknown work needs provider/runner evidence
before confirm_stopped or financial reconciliation. A refresh alone does not
restore model feedback. End-to-end paid model behavior was not tested.

## 2026-10-14 follow-up: repeated Run recovery notice

Rechecked the live file credential without inference: GET /models still returns
401. The same request c6ca4e00-a356-49b6-8694-90a092984122 remains
unknown/execution_unknown with the same model attempt and retained reservation.
No new model request was sent. Restart did not resolve either blocker.

Fixed the latest Run record retaining a misleading "is being recovered" notice
after recovery already returned unknown. The record now explicitly explains
that the earlier request is unresolved and status checking does not submit the
current question. The original request retains its own error and identity.
The existing Run regression test now verifies the latest record's explanation
and unchanged request pointer/submission count. No unknown work was closed,
replayed, or financially reconciled. Credentials still need correction locally;
provider/runner evidence is still needed to close the historical unknown.

## 2026-10-14 21:41 CST: Playwright live-browser investigation

Used the installed openai/skills Playwright CLI skill from the operator's
.agents/skills/playwright directory. A separate headed browser session opened
the real local frontend and authenticated normally through its local token host.
Recreated the known unsaved recovery pointer in this isolated profile only;
the backend response was not mocked. Installed a route guard against new
POST /api/sol/jobs before the controlled Run reproduction.

After that setup, actual UI fill + Run clicks produced POST /api/run 200,
then POST /api/sol/jobs/by-request/c6ca4e00-a356-49b6-8694-90a092984122/reconcile
200 with unknown/execution_unknown and null result. Draft remained intact,
Check request status remained, and the latest run showed the corrected blocked
feedback notice. No console errors or warnings were recorded. Screenshot and
snapshots are under output/playwright/feedback-debug/.playwright-cli/.

The browser's earlier network history also contained a new accepted job
df0938cd-b122-4bb0-91a4-6e6126237adc before the route guard/reproduction setup.
No CLI submit/click command was issued by the agent in that earlier interval;
its origin is not established. DB confirms that job ended failed/queue_expired
without a new model attempt. Do not describe the entire session as no new job
submission; only no new model inference attempt was verified.

IMPORTANT UPDATE: latest non-inference credential check now returns HTTP 200.
The prior 401 finding is no longer current. The unresolved job occupies active
capacity: Admission.ACTIVE includes unknown, claim counts it against active_jobs,
and configured active_jobs/model_calls caps are 1. This explains why a fresh
request can be admitted then expire without being claimed; clearing browser
storage or changing button text cannot fix the scheduler blockage.

No runtime data, slots, budget holds or policies were changed. Historical model
termination still requires authoritative provider/runner evidence per the
maintenance reconciliation contract before confirm_stopped. Authentication
success now does not establish the outcome of that historical call.


## 2026-10-14 21:49 owner-approved continuity; real feedback verified

Owner explicitly approved the prepared temporary concurrency increase and one
real verification request. Applied policy
`local-sixhour-week-budget-20261014-recovery-v5`: active_jobs/model_calls changed
from 1 to 2 at all four scopes. All monetary/resource budgets, quota anchors,
prices, deployment identity, amount-only manifest cap (5148223 microunits), and
all existing ledger job/attempt/slot rows were verified unchanged at application.
Applied under the installation lock after cooperative stop; no prepare/migration.
The previous policy and a review record are retained in local controlled-config.

Added an explicit policy-bound operator continuity grant for only
`c6ca4e00-a356-49b6-8694-90a092984122`. Authenticated config filters approvals by
unknown state, original principal/grant ownership, policy version and capacity.
Browser reload cannot submit work. A deliberate Ask/Run rechecks the old request,
archives its ID-only pending receipt before creating the new ID, and never closes
or replays it. The old unknown still consumes one slot and its 16683-microunit
model reservation remains unknown with actual usage null. A new unknown is not
covered by this old approval. Added no-store for the local host static assets so
updated client scripts are fetched after reload.

Verification: 74 frontend tests passed; 33 focused backend/API/local-host tests
passed; Ruff check/format and git diff --check passed. The earlier missing auth
error message was restored after regression tests found it absent from the file.

Real Playwright verification used a separate browser profile, the actual local
API/auth/worker/model, and the original unresolved recovery pointer. Reload
returned Ask Sol without submitting. One click on Run executed code then submitted
exactly one logical new tutor job, request
`3663289a-bba9-446b-9ab0-049a2723ffea`, job
`72b12385b4f817526864d23c30860a5bb059843349c4a5e5094ebe5633a1b591`.
It completed and the UI displayed Sol's explanation of result={} and KeyError A.
The normal tutor pipeline used three model attempts, all settled, totaling 9164
microunits in the local ledger; this is accounting evidence, not a provider bill.
The associated runner attempt also settled. No second logical model request was
submitted. Reload restored the same answer with Ask Sol available and no console
errors/warnings. Screenshot: output/playwright/feedback-debug/.playwright-cli/
page-2026-10-14T13-58-37-326Z.png.

Final live state at verification: completed28, failed14, unknown1; model slots
released90, unknown1; no active slot remains for the successful new request.
The old provider outcome remains unresolved. This is the approved temporary
continuity path, not evidence-backed closure or a refund of historical work.
Service is running on 8004/5177; user should preserve any editor draft and reload
the original page to load the updated script. Changes remain uncommitted/unpushed.


## 2026-10-14 quotation and exercise 1 follow-up

- Actual runtime config still authorizes continuation only for request c6ca4e00-a356-49b6-8694-90a092984122. Its unknown job, slot and reservation are unchanged. Exercises 2 and 3 have recent successful jobs; no later user exercise 1 submission appeared after the earlier authorized successful live test.
- Served JavaScript no longer includes the original recovery notice reported by the user. An old loaded browser tab is a plausible cause, but the user tab could not be inspected (Playwright extension unavailable).
- Added page build 20261014-quotation-2 and version parameters for client application scripts. Keep auth-client.js unversioned because the running local host injects authentication bootstrap by exact script-tag matching. No-store still applies to it.
- Quote previews now use a compact left border, 12px text, rendered safe inline Markdown and a 26px remove control. Preview is explicitly marked excerpt and limited to 280 rendered characters; the full Sol message is unchanged. The reference remains to the entire reply, not an arbitrary selected passage.
- Playwright CLI on the actual local frontend and actual recovery API, seeded with the original exercise 1 pending pointer, restored Ask Sol. Run code executed locally, then a network fixture intercepted new tutor admission and returned a marked UI-only reply. The old record remained separate and the quote rendered correctly. This was NOT another live provider inference.
- Screenshot: output/playwright/feedback-debug/quotation-browser-check.png. Frontend focused suite: 75/75 passed. git diff --check passed. No commit or push.

## 2026-10-14 final button styling and commit scope

The follow-up entry now has a visible rounded border and themed surface background,
12px text, 28px minimum height and compact padding. The quote remove control stays
26px. The served HTML and local authentication bootstrap were verified after this
CSS-only change. Interaction behavior is unchanged.

Owner requested committing all work at 22:28 CST. Backend recovery/context files,
frontend feedback/quotation changes and this chronological verification record are
included. Earlier uncommitted/no-push statements describe those earlier checkpoints.
Local credentials, runtime configuration, databases and Playwright output are not
part of the commits. No push was requested.
