# General controlled-runtime daily entry

## Step 1 — Audit (2026-10-11)

Inspected controlled_runtime.py, config.py, agent/llm.py, existing PowerShell
launchers and tests. PROVIDER selects openai_compatible, anthropic or local_stub.
Bedrock remains an explicitly rejected placeholder. OpenAI-specific thinking and
structured-output settings stay within that adapter. Metered billing requires
positive conservative policy prices; unknown usage retains reservations.

Current private profile uses DeepSeek through openai_compatible; supplemental
backend/.env contains the credential (presence only checked; never printed).
Read-only current installation: ports 8004/5177, 12 completed and 7 failed jobs,
no queued/running/unknown jobs. The fixed window expired; no pending grant.
No configuration, authorization, ledger or database changes were made to it.
Installed policy remains controlled-validation-run-cap-20261010-v3, price version
deepseek-flash-20261010-peak-ceil, positive input/output per-token bounds 1/2
microunits. These are private policy data, not constants added to the launcher.

## Step 2 — Daily wrappers and observable checks

Files: start-belay.ps1, stop-belay.ps1,
deployment/controls/start-controlled-runtime.ps1,
deployment/controls/stop-controlled-runtime.ps1, backend/app/controlled_runtime.py.
Checkout-relative defaults and override parameters reuse the existing entry.
Check never prompts. API/worker share resolved credentials; an absent default
supplemental credential file is optional. Check adds aggregate queue counts and
expired-window blockers. Start refuses expired windows, duplicate locks and
occupied ports. Stop verifies the installation receipt and held lock before
cooperative signaling. A separate ready event follows API startup and live worker
verification. Wrappers never invoke prepare, migrate, reset or renewal.

## Step 3 — Documentation and validation

Files: README.md, deployment/controls/README.md and this summary. Short daily
commands, credential precedence, queue caveat, first-use/migration boundaries,
provider limitations, readiness and troubleshooting. Student UI unchanged.

First targeted run: 46 passed / 1 failed / 0 skipped. The failed duplicate-start
test tried to hash an actively byte-locked Windows lock file; fixed the test
snapshot to exclude this synchronization file. Database, grants, keys and policy
remain included. Final targeted suites: **50 passed / 0 failed / 0 skipped**.
Includes the real registered OpenAI-compatible and Anthropic adapters with mocked
SDKs, local_stub controlled scenarios, saved/unsaved Run/Ask/recovery/authorization,
timeout holds and settlement, actual PowerShell wrapper invocation with fake
Python (custom paths, another checkout, optional credentials, missing EnvFile),
real installation-lock exclusion, simulated port conflicts, expired check without
file mutation, queued/unknown inventory without cleanup/replay, and simulated
server startup/readiness/cooperative shutdown/fatal worker handling. Each remote
adapter scenario asserts zero external network calls. No real provider request
was submitted this turn. Ruff lint/format checks pass for touched Python files.
The Windows lock-file test failure was a test issue; it was not a service crash.
Final type validation initially found two SQLAlchemy-row typing errors in the
new job-count dictionary; explicit conversion fixed them. Targeted mypy now passes.
After the final type/path adjustments, queue/expiry tests (2) and PowerShell
wrapper/default-path tests (2) passed again. Explicit relative DataDir now resolves
against PowerShell's current location after Set-Location, rather than the native
process working directory. The test covers another checkout with spaces.
`git diff --check` passes apart from an existing line-ending warning.

Daily commands from the repository root: `./start-belay.ps1 -Check`,
`./start-belay.ps1`, `./stop-belay.ps1` (second terminal, or Ctrl+C in foreground).
Default page/API remain 5177/dev-client.html and 8004. Current real environment
is still expired; this work does not authorize a new window. No real listener,
new paid response or production load was validated this turn. Existing student
UI and all preexisting changes remain intact. No commit was created.

The shell batch used to write documentation was rejected by automatic approval
(blocked by policy); documentation is edited through reviewable file patches.
No service launch is attempted through another command/tool. Prior automatic
demo startup was also rejected; actual listener startup remains unverified this
turn. Lifecycle testing uses simulated transports/servers and real worker-thread
supervision, without remote model calls. No push or deployment. Commit: none.
