# Local short-period + weekly budgets: candidate and implementation summary

**Later explicit authorization applied:** the user chose different values from
the alternatives below: additional USD5, cumulative ceiling USD5.148223,
USD1/six hours and USD5/week, without token/run/wall-time increases. See the
[application/verification record](local-budget-authorization-20261011-summary.md).
The original proposal and its unapproved status at the time are retained below
as history, not an instruction to apply either earlier option.

Status: **awaiting monetary/resource authorization**. The previous USD5 proposal
was never approved. No live policy or cumulative ceiling was changed by this
round. This is a local development feature, not a formal course entitlement.

## Step 1 — current blockage (read-only)

Snapshot: October 11, 2026, 10:20:38 Asia/Shanghai. Existing SQLite was opened with
`mode=ro`, without starting a worker or calling a provider.

| Constraint | Limit | Used | Unknown-held | Available |
|---|---:|---:|---:|---:|
| Across-period cumulative money | USD0.148223 | USD0.131837 | USD0 | USD0.016386 |
| Each of deployment/institution/class/learner, current period money | USD0.148223 | USD0.017362 | USD0 | USD0.130861 |
| Each scope's tokens | 200000 | 16662 | 0 | 183338 |
| Each scope's sandbox runs | 50 | 8 | 0 | 42 |
| Each scope's sandbox wall milliseconds | 300000 | 5906 | 0 | 294094 |

Persisted mode remains `amount_only`, without an inference expiry. Latest denial
is `budget_exhausted` at 10:10:59; the three preceding denials have that same code.
There are 13 completed / 11 failed jobs, no queued/running/unknown jobs. Recent
known call reservations were USD0.017989–0.022243, exceeding current cumulative
headroom. The small cumulative cap is the evidence-backed likely blocker; scoped
counters are not exhausted. The old rejection table stores only code/time, not
denied amount, dimension or task ID, so exact historical attribution is not
available. This does not establish a DeepSeek account-balance problem.

Two earlier failed jobs had already settled one model call each (USD0.004144 and
USD0.004166); a failed response can still consume funds. Do not retry them as part
of this update. Snapshot DB hash:
`a0c5679bcfea27623ffe52e02e5144bf951d3cdac133e83752a5b1c9cae97877`.

## Step 2 — concrete choices, neither approved

**A. Smallest immediate bridge:** authorize **USD0.50 additional**. Keep
amount-only mode and leave the new dual quotas disabled for this bridge.

- Cumulative ceiling: USD0.148223 -> **USD0.648223**.
- Available at the snapshot: USD0.016386 -> **USD0.516386**.
- Four existing scoped currency ceilings: USD0.148223 -> USD0.648223 each.
- Companion local limits per existing period: tokens 200000 -> 1000000;
  runs 50 -> 300; wall milliseconds 300000 -> 1800000 at each layer.
- Estimated 25–40 further logical feedback tasks with margin. This restores a
  finite working allowance; it is not a recurring-quota solution.

**B. Recommended dual-quota trial:** authorize **USD4.00 additional**, with
**USD0.50 per fixed six hours and USD2.00 per fixed week**.

- Cumulative ceiling: USD0.148223 -> **USD4.148223**.
- Available at the snapshot: USD0.016386 -> **USD4.016386**.
- Four scoped currency ceilings: USD0.148223 -> USD4.148223 each, still bounded
  by the cumulative ceiling and both model quotas.
- Companion local limits per existing period: tokens -> 5000000; runs -> 2000;
  wall milliseconds -> 3600000 at each layer. This wall-time budget is accumulated
  sandbox execution, not an access/authorization timeout.
- Count existing usage in the currently open buckets: short-period available
  USD0.482638; this week's available USD1.868163 (all USD0.131837 historical
  consumption here falls within this week). Enabling a quota is not a clean slate.
- Estimate 25–40 tasks per full six-hour allowance, 100–160 per full weekly
  allowance; about 200–320 tasks from the new USD4 overall. This funds roughly two
  full weekly ceilings, not unlimited future weeks. Existing-history/current-week
  headroom and reservations can reduce those numbers.

Alternative short period: **USD0.50 per day**, same weekly ceiling/funding; slower
testing pace, no same-day refresh. Do not simultaneously stack this daily quota
with the six-hour candidate unless separately designed and approved.

Estimates use 12 completed paid local tasks, three model calls each: mean booked
cost USD0.009263, range USD0.008663–0.011413. Planning uses USD0.0125–0.02/task for
longer context, retries, partial failures and conservative pre-dispatch headroom.
These are ledger estimates under installed pricing, not current vendor quotes
or guaranteed request counts. One Ask/Run feedback task contains several model
attempts, each independently reserved and settled.

Neither option changes prices, provider, deployment, DB, access permissions,
queue/rate/concurrency limits, single-run timeout or retention. No amount is
infinite. New ceiling = old ceiling + approved increment, never used amount +
an assumed replenishment. Old remainder is retained once, unknown holds deducted.

## Step 3 — optional reuse of the coordinator

Files: `backend/app/controls/contracts.py`, `backend/app/controls/ledger.py`,
`backend/tests/test_model_budget_quotas.py`.

Added optional `Policy.model_quotas` (default null). It applies deployment-wide
model currency quotas in the **same existing reservation transaction** as the
cumulative and scoped checks. Both windows must pass; no separate counter,
scheduler, database reset or schema migration. Existing policies remain disabled.

Candidate B policy fragment (proposal only, not installed):

```json
"model_quotas": {
  "short_period_seconds": 21600,
  "short_anchor_utc": 57600,
  "short_microunits": 500000,
  "week_anchor_utc": 316800,
  "week_microunits": 2000000
}
```

- Fixed buckets, **not rolling look-back windows**. Six-hour boundaries in
  Asia/Shanghai are 00:00, 06:00, 12:00, 18:00; daily alternative is 00:00.
  Weekly boundary is Monday 00:00 Asia/Shanghai. Start is inclusive, end exclusive.
  The anchor integers encode that alignment in UTC epoch seconds. Shanghai has
  no daylight-saving transition; other timezones/DST require a reviewed alignment
  strategy, not a promise that these fixed UTC offsets follow local clocks.
- Bucket start = anchor + floor((now - anchor)/seconds)*seconds. Restart does not
  move the anchor. The legacy scoped period stays 86400 seconds UTC-anchored
  (08:00 Shanghai), independently; no migration/change to historical period IDs.
- A request spanning a boundary is charged to its original reservation timestamp.
  Old settled attempts count in the applicable new buckets even if created before
  this feature. Unknown reservations from **all** periods encumber both windows
  until reconciliation; they are never refunded at midnight or week rollover.
- An exact fixed boundary permits one bucket's allowance just before it and the
  next just after. Weekly, cumulative, queue and concurrency controls still
  apply. Rolling windows would smooth this but are not implemented here.
- Effective available money is the minimum of cumulative, short, weekly and
  applicable existing scoped headroom, minus the next required reservation.
  Short refresh does not reset weekly use; weekly refresh does not add money to
  cumulative funding. Once cumulative funding is exhausted, explicit new approval
  is still required. Option B raises that ceiling sufficiently for the initial
  trial instead of leaving USD0.148223 silently blocking the new quotas.
- This is deployment-local testing capacity. Learner entitlements/course funding
  need their own agreed scopes and lifetimes; these values are not student defaults.

## Step 4 — explicit, repeat-safe update command prepared

Files: `backend/app/controlled_runtime.py`, root/deployment PowerShell launchers,
`backend/tests/test_controlled_runtime.py`. No live grant file has been generated.

`authorize-budget` supports amount-only grants without a time window. It requires
an explicit increment, expected old ceiling/deployment/policy version, retain-old-
balance decision, unique authorization ID and the exact reviewed new policy.
An identical ID/content retry never adds money twice. A conflicting ID or changed
baseline rejects. It takes the host lock and checks ports, receipt ownership and
active/queued tasks. Unknown records/holds remain untouched. No model or listener
starts. Price, legacy period and traffic changes are rejected by this operation.

It calls existing `Ledger.update_policy`, then atomically replaces the manifest
with the approved new cumulative ceiling and grant history. These are **not one
cross-file transaction**. If manifest replacement fails, the old smaller ceiling
remains enforced (new scoped/quota policy may already be present). Retrying the
identical files completes the same grant; it never computes an extra increment
from a fresh balance. Restart does not perform a grant or retry a failed task.

After confirmation, prepare the two reviewed private files at the paths below;
they do not yet exist as approved inputs. From the repository root:

```powershell
# Available now: read-only check. This does not remove the existing blocker.
.\start-belay.ps1 -Check

# After explicit approval and generation of the reviewed private files:
.\stop-belay.ps1
# Wait for that instance's foreground process to exit.
.\start-belay.ps1 -BudgetAuthorization .\deployment\local\controlled-config\approved-budget.json -BudgetPolicy .\deployment\local\controlled-config\approved-budget-policy.json
.\start-belay.ps1 -Check
.\start-belay.ps1
```

An already stopped host need not be stopped again. Do not stop unrelated services,
delete receipts to evade checks, or re-run prepare. Preview/API remain 5177/8004.
The API and worker need the next controlled restart to load changed settings;
the user submits a **new** test manually. `checked:true` is not `ready:true`.

## Step 5 — verification / limitations

- Initial isolated quota/ledger/window suite: 29 passed, 1 skipped (PostgreSQL
  cross-process test requires an isolated `CONTROL_TEST_DATABASE_URL`).
- First broader run: 89 passed, 3 failed, 1 skipped. The three failures were test
  fixtures probing actual default ports now occupied by the user's running host.
  Corrected the fixture to use separate ephemeral test ports; no user service was
  stopped or changed. An overlapping old-fixture run was interrupted.
- Final focused rerun: **94 passed, 0 failed, 1 skipped**, 155.97 seconds, covering
  `test_model_budget_quotas`, `test_controls_ledger`, `test_controls_execution`,
  `test_controlled_runtime`, `test_provider_capabilities`, `test_inference_window`.
  The skip remains the isolated PostgreSQL cross-process test. After extending
  PowerShell grant-argument coverage, its targeted rerun also passed (1/1).
  Ruff and `git diff --check` passed; mypy passed for all three changed runtime
  modules (`controlled_runtime`, controls contracts and ledger).
- Coverage: short and weekly boundaries, preexisting usage, late settlement,
  unknown holds, cumulative exhaustion after weekly refresh, scope isolation,
  existing learner caps, concurrent reservations, version/restart stability,
  daily alternative, model stub dispatch, grant idempotency and manifest-failure
  recovery. No live inference, paid request, old task replay or live policy update.
- Formal teaching: record configurable learner periods during valid enrollment,
  cumulative class/course funding and immutable history as candidates for Greg.
  Semester/access rules, learner-specific refreshed quotas, course-budget lifetime
  interfaces and administrator UI remain unimplemented. See the separate
  [local/course responsibility discussion](local-and-course-budget-plan.md).
- No commit, push or deployment. Pre-existing modifications retained. Remaining
  immediate dependency: explicit approval of A or B (or other exact amounts),
  including its companion local resource caps, before preparing/applying live
  authorization files.

Final read-only live-state check: ceiling 148223, consumed 131837, unknown-held 0
microunits; `model_quotas` is still absent/null in the actual paid policy and
version remains `controlled-validation-run-cap-20261010-v3`. Manifest SHA-256
stayed `0f90e47e3d3785ae115f3e4408d7d1ba1083abe3a71d590caf3706dd7e6e790e`.
The existing user-started 8004/5177 process was left running; this round did not
write the real ledger or invoke the new grant command against it. The new code
requires a later controlled restart if an approved configuration is installed.
