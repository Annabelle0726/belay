# Optional local inference deadline — implementation summary

## 1. Audit and scope

- Goal: keep the existing cumulative monetary ceiling while removing repeated short local authorization renewals.
- Evidence: `controls/runtime.py` already treats an inference expiry of zero as no deadline; `controls/ledger.py` independently enforces the cumulative ceiling, including prior accounting periods and unknown reservations. No new accounting system is required.
- Gap: `controlled_runtime.environment` restores an already persisted window over env settings. `authorize-window` grants additional money and is inappropriate for a time-only change.
- Existing UI and all pre-existing working-tree changes are retained. No model, price, identity, R2 retention or settlement changes are intended.

## 2. Explicit budget-mode transition

- Files: `backend/app/controlled_runtime.py`, `start-belay.ps1`, `deployment/controls/start-controlled-runtime.ps1`.
- Added `use-amount-only-budget` / `-UseAmountOnlyBudget`: stopped installation only, finite cumulative cap required, reject pending grants or queued/running/cancel-requested work. Unknown jobs are left intact.
- Existing timed profiles use their persisted cap, never a replacement env cap. The previous window is archived in `budget_mode_history`; the new `amount_only_budget` pins the same ceiling without a fake future deadline. Repetition is idempotent.
- Only `runtime.json` is atomically replaced. No schema, DB, prices or ledger update; no listeners or inference. Start/check honor the persisted mode, including when the old env still specifies 7200 seconds. Existing bounded-window behavior remains.
- Verification: pending isolated tests. No current installation change yet; no commit made in this step.
- Remaining: regression checks, team documentation and a guarded local transition after verification.

## 3. Isolation checks and documentation

- Files: `backend/tests/test_controlled_runtime.py`, `backend/tests/test_inference_window.py`, root/team README, runtime guide, env example, previous extension proposal (historical status note only).
- Tests cover persisted cap precedence, idempotent conversion, unknown task/hold preservation, byte-identical DB/identity files, atomic-write failure, running-host lock exclusion, pending/active-work guards, bounded-mode regression and PowerShell delegation. Model stubs exercise successful settlement then exhaustion across accounting periods, retaining unknown reservations.
- First run: one new test failed because its synthetic ceiling of 100 microunits could not cover the existing conservative 1024-byte framing reservation. Increased only the isolated test allowance to 10000; the follow-up inference/window + wrapper run passed 11/11. No real allowance was changed to make tests pass. Full focused rerun is in progress.
- Local read-only audit: ceiling 148223, consumed 114475, unknown-held 0 microunits; 12 completed / 7 failed jobs and no queued/running work. Matching old receipt PID 31216 is absent and ports 8004/5177 have no listener. The conversion now requires exclusive host lock plus free ports and matching receipt nonce; it retains stale receipt evidence instead of deleting it. A held lock or mismatching nonce rejects the operation.
- Local configuration not yet converted at this step; no commit, paid request or service launch.

## 4. Verification completed and local configuration applied

- Isolated command: from `backend`, `python -m pytest tests/test_controlled_runtime.py tests/test_inference_window.py tests/test_provider_capabilities.py -q --tb=short -o addopts=''`.
- Final result: **62 passed, 0 failed, 0 skipped**, 170.79 seconds. Includes mocked SDK/provider execution and lifecycle checks; no real listener or paid provider request. The earlier failed new test and its correction are recorded above.
- `ruff check` passed for the three touched Python files; `mypy app/controlled_runtime.py --follow-imports=silent` passed. `git diff --check` passed. Full repository suite, live browser and live provider replies were not run for this configuration-only change.
- After passing isolation tests, ran the real wrapper **only** with `-UseAmountOnlyBudget`, then `-Check`. Conversion returned `additional_microunits: 0`, `database_changed: false`, `model_calls: 0`, `listeners_started: false`. The stale matching receipt remains intact.
- Effective private profile now reports `inference_window: {state: disabled, mode: amount_only}`, `start_allowed: true`, empty blockers; original provider/models remain unchanged. Jobs remain 12 completed / 7 failed; no queued work. This is preflight, not a running-service or paid-response verification.
- Before/after SHA-256 comparison of 63 local files (runtime/config directories and `backend/.env`, excluding the lock file): **only runtime.json changed; 62 files unchanged; no added files**. This includes the shared DB, identity files, execution key, original receipt, pricing configs and credentials. Original deployment ID is retained. Shared DB SHA-256 remained `29b990fb3aab51cf483b039fc4bd14c58ebf73560a71586e62a241bf3799c208`.
- Financial state retained: cumulative ceiling **148223 microunits (USD0.148223)**; consumed **114475 (USD0.114475)**; unknown-held **0**; available **33748 (USD0.033748)**. This remainder can still be insufficient for a conservative per-call reservation; removal of expiry does not guarantee any particular task will fit. No new grant, period change, reset, reconciliation or re-execution occurred.
- The private env still contains the historical 7200-second setting; persisted amount-only mode intentionally overrides it and pins the existing ceiling for API and worker. No key copying or private config files were added to Git.

## Daily use and remaining limits

From the repository root:

```powershell
.\start-belay.ps1 -Check
.\start-belay.ps1
# In a second terminal when ready to stop:
.\stop-belay.ps1
```

No further conversion or prepare is needed for this installation. It was stopped
at the time of conversion; the next manual start loads the new mode. Wait for
`ready:true` / `worker_alive:true`; preflight is not that readiness signal.
Frontend: `http://127.0.0.1:5177/dev-client.html`; API: `http://127.0.0.1:8004`.
Review queued work on every start because future eligible queued jobs can execute;
unknown jobs are not automatically resubmitted. No automatic startup was attempted.

Bounded profiles retain the existing fixed-window behavior (up to 7200 seconds).
A reverse amount-only-to-bounded transition is not added here and would require
separate review. No production/distributed load acceptance, admin page, daily
grant system, model change, UI change, paid test, push or deployment. No commit
was made; existing uncommitted work remains intact.
