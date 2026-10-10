# Dev-client curriculum CORS repair — 2026-10-10

## D0 — actual service and failure diagnosis

Goal: inspect the existing service without redoing Stage C or touching databases.
Starting branch: `feature/ui-conversation-preview` at `fcf69a8`; no tracked local
changes. The pre-existing untracked controls integration review stays untouched.
Repair branch: `fix/dev-client-curriculum-startup`. Files changed in D0: this record.

Both loopback ports 8002 and 5175 belong to PID 9824, Python 3.12, launched from
`backend` by the user's PyCharm PowerShell with `-m app.local_dev --save-dialogue
--api-port 8002 --frontend-port 5175 --data-dir ..\deployment\local\ui-preview`.
The process environment selects `datascience` and CORS origin
`http://127.0.0.1:5175`; its loaded middleware still accepts old `.env` origins.
The existing process predates the final Stage C commits; loaded code/configuration
is not assumed to match the checkout. Its controls flags are not enabled; this
repair does not enable them or change saved/unsaved task behavior.

Actual browser curriculum request: GET with Authorization, Content-Type,
X-Belay-Class and X-Belay-Institution. Matching OPTIONS returns **400 Disallowed
CORS origin**, Vary: Origin, allowed methods/headers, and no Allow-Origin.
Old localhost:5173/3000 origins receive 200. An unauthenticated GET returns 503
before repair (incomplete captured authentication configuration). CORS is the
existing application middleware, before route dependency authentication; no proxy
or authentication interception of OPTIONS was observed. No origin wildcard is
needed. Font/extension warnings are unrelated.

Cause reproduced in a fresh interpreter: loading `datascience` imports
`core.runner -> controls.runtime -> config` before `local_dev.configure` sets its
host/auth/database environment. Later environment assignments do not update the
already-created Settings object. Thus environment inspection alone falsely looks
correct. Skeleton lacks this import path and would mask the failure.

The actual data-science curriculum contains the original three exercises:
`ds-foundations` (01 · Grouped summaries), `ds-regression` (02 · Held-out
regression), `ds-mlp` (03 · Tiny MLP from scratch). No teaching content changed.

Validation: live matching preflight and Chromium failure reproduced; isolated
import-order reproduction passed. Repair and post-restart browser/auth checks
remain pending. No database initialization, migration, restore or cleanup was run.
Commit: pending D1 repair commit.

## D1 — minimal startup order fix and regression

Goal: make the already selected local origins/auth configuration effective for
the real teaching pack. Files: `backend/app/local_dev.py`,
`backend/tests/test_local_dev_cors.py`, this summary.

Moved the existing pack loading and unchanged synthetic grant generation after
the launcher's complete environment assignment. No CORS wildcard/default list,
middleware order, authentication/authorization rule, curriculum, conversation
policy or budget setting changed. No frontend code changed. The only application
behavior change is reading the intended startup configuration before transitive
imports capture it.

The regression uses a fresh interpreter and the actual `datascience` pack, starts
with an incorrect old origin, and exercises the actual application middleware and
signed auth. It stubs migration/init solely in that test, forbids SQL connections,
and asserts no demo database was created. It failed before repair on the stale
origin and passed afterwards. Exact-origin preflight succeeds with all actual
browser header names; another origin is rejected; unsigned GET stays 401 and
ungranted class stays 404; signed GET returns the original three exercise IDs.

Verification: **169 passed, 0 failed, 0 skipped** across this regression and the
existing identity/isolation suite. Ruff check and format passed (156 files);
mypy passed (149 source files). Initial format check identified only formatting
of the new test; formatted and rechecked successfully. No full Stage C,
PostgreSQL, inference or load suite was rerun for this startup-only change.
Pytest's harness uses its disposable test database; existing local databases were
never initialized, migrated, restored, cleared or used as test databases.

Remaining operational step/evidence: refresh the identified local preview without
running its normal provisioning/migration path; see D2. This commit records D0/D1;
its number will be recorded in D2 after commit.

## D2 — non-provisioning restart and actual browser acceptance

D1 repair commit: `545a722`. Goal: make the current preview usable without
initializing/restoring/migrating databases. Files changed in D2: this summary;
an untracked, private purpose-named restart helper/snapshot outside the repository.
No application code changed after D1 verification.

Confirmed PID 9824's exact command/cwd immediately before stopping only that
preview. Captured its full environment privately without printing secrets. Kept
the original backend/frontend origins, data directory, datascience pack, SQL store,
saving flag/policy, authorization file and controls flags. Restart uses a private
one-off `resume_dev.py` helper in
`C:\Users\ASUS\AppData\Local\Temp\belay-curriculum-restart-fl0be4t2`.
It does not call `configure`, dialogue migration, ledger initialization or
`create_all`; instead SqlStore's startup hook checks existing table names through
SQLite `mode=ro`. Normal business identity/authorization dependencies remain.
Missing files/schema fail rather than provision. Only the memory-only local
signing key's public counterpart rotates; original grant rules are not rewritten.
The initial helper launch lacked the backend import path and exited without
touching data; its path was corrected and the replacement started successfully.
Subsequent live requests/browser checks passed. No unrelated service was stopped.

Replacement PID **31124** listens on loopback **8002 and 5175**. Live verification:

| Check | Actual result |
| --- | --- |
| OPTIONS GET with authorization, content-type, x-belay-class, x-belay-institution | 200; Allow-Origin exactly `http://127.0.0.1:5175` |
| Different origin `http://127.0.0.1:5176` | 400; no Allow-Origin |
| Curriculum without bearer | 401; correct CORS response |
| Signed curriculum with original class | 200; original three exercises |
| Signed request with ungranted class | 404 |
| Existing optional-saving configuration | 200; enabled as before |
| Task configuration | 503 `jobs_disabled`; correct CORS, inherited configuration unchanged |

Real Chromium loaded `http://127.0.0.1:5175/dev-client.html` and received the
curriculum HTTP 200 with the exact Allow-Origin header. All three dropdown options
match D0 and each shows its prompt/starter. No page script errors. Requests outside
loopback were blocked during this verification. Screenshot inspected and kept
privately outside Git. No Ask, code Run or model request was made. No paid model
was called. Browser observation supersedes the earlier reproduced failure.

SHA-256 checks before restart and after browser verification show unchanged:
`deployment/local/ui-preview/demo.sqlite3`, root/backend `qimvp.db`, authorization
JSON, deletion ledger, backend `.env`, and the pre-existing untracked review.
Only `public-key.pem` differs as expected. No database, key, token, logs, environment
snapshot or student data is staged/committed. No main update, remote push, deploy,
branch deletion or Stage C reintegration occurred.

Remaining scope: the original service has controlled jobs disabled; its task-status
notice/503 is a separate configuration issue, not a curriculum/CORS/auth/router/
pack failure. It was not enabled or retested with inference. Saving operations,
budget tasks, PostgreSQL, paid providers and full Stage C acceptance were not part
of this repair. The ordinary launcher's existing provisioning behavior has not
been redesigned; this repair deliberately used the one-off non-provisioning
restart to honor the no-database-change constraint.

Recheck: keep the current preview running, open
`http://127.0.0.1:5175/dev-client.html`, hard-refresh, and inspect Network:
`OPTIONS http://127.0.0.1:8002/api/curriculum` → 200 and authenticated GET → 200.
Verify Grouped summaries, Held-out regression and Tiny MLP in the dropdown. No
model call is necessary. Backend base: `http://127.0.0.1:8002`.
