# Approved local budget update — 2026-10-11

## 1. Authorization and baseline

The user explicitly approved this new local grant (not the earlier unapproved
USD5 suggestion): add USD5 to the existing USD0.148223 cumulative ceiling,
retain amount-only mode, enable USD1 per six hours and USD5 per week, and set
each existing scope's periodic currency ceiling to USD5.148223.

No token/run/wall-time increases were approved by this message. They remain
200000 tokens, 50 runs and 300000 wall milliseconds per existing accounting period
at each deployment/institution/class/learner level. Existing identity, class
isolation, prices, model selection, traffic, timeouts and retention remain.

Read-only baseline at 10:39:47 Asia/Shanghai: consumed 131837 microunits;
unresolved-held 0; 13 completed / 12 failed jobs, no queued/running/unknown jobs.
The matching receipt and listeners identified PID 36236 as the local Python
runtime on 8004/5177. The old policy was
`controlled-validation-run-cap-20261010-v3` and cumulative cap 148223.

## 2. Prepared files and isolated verification

Private, ignored files (no credentials):

- `deployment/local/controlled-config/approved-budget-20261011.json`
- `deployment/local/controlled-config/approved-budget-policy-20261011.json`

Authorization ID: `local-five-dollar-sixhour-week-20261011`. It pins the expected
old cap, deployment and policy, adds exactly 5000000 microunits, and explicitly
retains unused balance. The policy is copied from the installed policy with only
version, four currency ceilings and `model_quotas` changed. A differing existing
approval file is rejected rather than overwritten.

Tracked code change this step: one exact-value isolation test added to
`backend/tests/test_model_budget_quotas.py`. It verifies historical usage under
the approved amounts, short refresh preserving the weekly total, week rollover
preserving the cumulative ceiling, and no automatic new funding.

Verification command, from `backend`:

```powershell
python -m pytest tests/test_model_budget_quotas.py tests/test_inference_window.py tests/test_controlled_runtime.py::test_amount_only_grant_is_explicit_retryable_and_preserves_old_spend tests/test_controlled_runtime.py::test_root_powershell_wrappers_delegate_paths_without_preparing -q --tb=short -ra -o addopts=''
```

Result: **27 passed, 0 failed, 0 skipped** in 25.37 seconds. Includes isolated
grant retries, unknown-hold preservation, manifest-failure recovery and wrapper
delegation. No real model calls or listeners. The previous broader run was 94
passed / 1 PostgreSQL cross-process test skipped; that PostgreSQL coverage was
not rerun here and remains unverified for this local SQLite update.
Ruff lint/format checks for the added test and `git diff --check` also passed.
Both private approval files are confirmed ignored by Git.

## 3. Applied using the existing controlled operator entry

Used `./stop-belay.ps1` to request cooperative shutdown of the matching host.
Confirmed PID/listeners and receipt disappeared before modifying configuration.
No unrelated service was stopped; no process was killed by port.

Executed from the repository root:

```powershell
.\start-belay.ps1 -BudgetAuthorization .\deployment\local\controlled-config\approved-budget-20261011.json -BudgetPolicy .\deployment\local\controlled-config\approved-budget-policy-20261011.json
.\start-belay.ps1 -Check
```

The grant returned authorized/unchanged:false, total 5148223, added 5000000,
model_calls:0 and listeners_started:false. Repeating the identical authorization
returned unchanged:true; the cap and history entry were not duplicated.

Installed policy: `local-sixhour-week-budget-20261011-v4`. Price version remains
`deepseek-flash-20261010-peak-ceil`. Current model selection remains
openai_compatible / deepseek-flash; no provider request verified the key or model.
The check reports amount-only mode, no deadline, start_allowed:true, no blockers,
no queued work and unknown_work_replayed:false. It is preflight, not readiness.

Comparison after shutdown versus after application:

- Only `control_configuration` changed among 20 DB tables. All **19 other tables**
  have identical row counts/content hashes, including attempts, jobs, saved
  conversations and existing unknown-accounting records. No schema migration.
- Only `amount_only_budget` and `budget_grant_history` changed in runtime.json;
  deployment and previous authorization history remain unchanged.
- All 62 other snapshot files (including env files, identity/credential files,
  execution key and original pricing files) remained byte-identical.
- No prepare, ledger clearing, settlement rewrite, old-job replay or new task.

The runtime's persisted ceiling takes precedence over historical env cap values.
The installed DB policy is authoritative for quotas; initial prepare examples
and earlier private policy files are not silently overwritten or rerun.

## 4. Effective allowance and fixed boundaries

Post-update snapshot: **2026-10-11 10:44:08 Asia/Shanghai**.

| Check | Cap | Used | Unknown-held | Available |
|---|---:|---:|---:|---:|
| Cumulative, no expiry | USD5.148223 | USD0.131837 | USD0 | USD5.016386 |
| Six-hour bucket | USD1 | USD0.017362 | USD0 | USD0.982638 |
| Weekly bucket | USD5 | USD0.131837 | USD0 | USD4.868163 |

Each existing scope's currency cap is USD5.148223. Its legacy period remains
86400 seconds, UTC-anchored; the new short/week buckets are separate constraints.

Timezone: **Asia/Shanghai (UTC+08:00)**. Fixed six-hour boundaries at
00:00/06:00/12:00/18:00; fixed weekly boundary Monday 00:00. Start inclusive,
end exclusive. Current short interval is October 11 06:00–12:00; current week
October 5 00:00–October 12 00:00. The anchors are 57600 and 316800 UTC epoch
seconds. Existing usage in these intervals was counted, not erased at activation.

Both quotas, cumulative funding and all existing scope/resource controls must
pass before a reservation. Short refresh does not reset weekly use. Weekly
refresh does not reset cumulative use or add USD5. Restart does not move the
boundaries or repeat the grant. Unknown holds carry across boundaries until
reconciliation. Future exhaustion of the finite total requires new explicit
authorization. This is local testing configuration, not a student/course policy.

## 5. Manual restart and remaining unverified scope

The old service is stopped. Previous automatic launch was rejected as
`blocked by policy`; no alternative launch mechanism was used. From the
repository root, the user can now run:

```powershell
.\start-belay.ps1 -Check
.\start-belay.ps1
```

Wait for `ready:true` and `worker_alive:true`, then open
`http://127.0.0.1:5177/dev-client.html` (API `http://127.0.0.1:8004`). Submit a
new test manually; do not replay unknown tasks. Stop via Ctrl+C or
`./stop-belay.ps1` from a second repository-root terminal. No additional grant
command or prepare is needed for normal launches.

Post-update running-worker readiness, browser feedback and paid responses were
not tested by this agent. The original small non-money resource limits may still
block requests; they were intentionally not increased without authorization.
No formal course/semester policy or administrator page was added.

Docs updated: root README, team controls README, this summary and a status note
on the earlier proposal. Existing changes retained. No commit/push/deployment.
