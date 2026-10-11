# Local development and future course quotas

Status: proposal pending operator approval, 2026-10-11. No allowance has been
increased. This document separates a local developer's finite testing budget
from the future learner/course policy to be agreed with Greg.

**Follow-up:** the USD5 suggestion below was not approved. The user's newer
direction is short-period plus weekly local quotas; see the
[current plan](local-period-budget-plan.md). Keep this earlier analysis as history,
not authorization to add USD5. The new explicit amount-only grant entry is now
prepared in code; the former implementation gap below describes the earlier state.

## 1. Read-only local audit

Snapshot: 2026-10-11 10:01:32, Asia/Shanghai. Queried the existing SQLite file
through `mode=ro`; no application worker, SDK or inference was invoked.

The persisted mode remains `amount_only`, with no inference authorization
deadline. The cumulative ceiling is USD0.148223; settled consumption USD0.131837;
unresolved reservations USD0; remaining USD0.016386. These are Belay ledger
amounts under the installed price policy, not a provider account balance or invoice.

The latest three rejection records are `budget_exhausted`, at 09:50:14,
09:50:35 and 09:51:08 on October 11. The last two model-bearing failed tasks each
settled one model call (USD0.004144 and USD0.004166) before failing; the final
failed task has no model attempt. Failure does not imply zero expenditure.
Earlier `inference_window_expired` records belong to October 10 and must not be
used to explain these new rejections.

Current policy: `controlled-validation-run-cap-20261010-v3`; price version
`deepseek-flash-20261010-peak-ceil`; input/output prices 1/2 USD microunits per
token. Prices were read from the installed policy, not independently verified
against current provider prices. No pricing change is proposed here.

The deployment, institution, class and learner each currently have the same
periodic limits and usage (this installation has one scope chain):

| Unit | Limit per layer | Used in current period | Unresolved | Remaining |
|---|---:|---:|---:|---:|
| USD | 0.148223 | 0.017362 | 0 | 0.130861 |
| Tokens | 200,000 | 16,662 | 0 | 183,338 |
| Sandbox runs | 50 | 7 | 0 | 43 |
| Sandbox wall time, ms | 300,000 | 3,820 | 0 | 296,180 |

The existing accounting period is 86400 seconds, UTC-anchored; this period began
October 11 at 08:00 Shanghai time. Its monetary remainder is **not** additional
money: the across-period cumulative ceiling still limits the whole installation
to USD0.016386 available. Removing a deadline did not remove these other caps.

`Ledger.reserve_in` checks the cumulative ceiling before the four scoped limits.
`model_call` reserves UTF-8 prompt bytes plus 1024 framing units and the output
bound at the configured prices before dispatch. Recent successful model-call
reservations reached USD0.022243; the two recent partial tasks reserved
USD0.017989 for their first call, already greater than the present remainder.
The evidence strongly points to insufficient cumulative reservation headroom,
while the scoped counters have substantial headroom. **Exact rejection-layer
attribution is not recorded:** `control_rejections` stores only code/time, not
scope, unit, requested amount or task ID; denied reservations create no attempt
row. Do not present the inferred layer or the denied amount as an exact logged
fact, and do not attribute it to a provider balance. Future content-free rejection
diagnostics could record those fields, but are not implemented in this round.

Evidence locations: `backend/app/controls/ledger.py` (`rejections`, `reserve_in`,
`_usage`, `update_policy`), `backend/app/controls/runtime.py` (`model_call`),
`backend/app/controls/worker.py` (job ID used as ledger operation),
`backend/app/controlled_runtime.py` (persisted amount-only ceiling).

## 2. Local recommendation — NOT authorized or applied

Recommend **adding USD5.00** to the existing cumulative ceiling, retaining the
unused balance. At this snapshot:

| Additional authorization | New cumulative ceiling | Available after existing consumption | Planning range of further logical feedback tasks |
|---|---:|---:|---:|
| USD1.00 | USD1.148223 | USD1.016386 | 50–80 |
| **USD5.00 (recommended)** | **USD5.148223** | **USD5.016386** | **250–400** |
| USD10.00 | USD10.148223 | USD10.016386 | 500–800 |

These are incremental amounts, not a replacement allowance on top of which the
old remainder is added again. New ceiling = old ceiling + explicitly approved
increment; available = new ceiling minus all settled usage and unresolved holds.
Re-read usage at update time; new activity can reduce availability, never increase
the approved ceiling. No expiry, automatic renewal or new daily grant is proposed.

Estimation basis: 12 completed, nonzero-cost tasks in the local ledger (excluding
the zero-price stub task) each used 3 model calls. Their settled task costs range
USD0.008663–0.011413, mean USD0.009263; mean tokens 8810.25. Simple division would
give roughly 540 similar tasks for USD5. The recommendation instead plans at
USD0.0125–0.02 per task (250–400 tasks), allowing for longer context, internal
retries/refinement, failed partial tasks and conservative reservation headroom.
This is a workload estimate, not a guarantee or a current vendor price quote.
Run feedback is one logical task; its planner/reasoner/evaluation calls are
separate accounted model attempts. Sandbox executions can also occur inside a
task, in addition to the student's initial Run.

For that USD5 proposal, also propose these **local-only** finite scoped limits
at all four existing layers, subject to the same approval:

- Money: USD5.148223 per existing accounting period, additionally bounded by
  the unchanged-mode cumulative ceiling of USD5.148223 across all periods.
- Tokens: 10,000,000 per existing period (currently 200,000).
- Sandbox runs: 3,000 per existing period (currently 50).
- Aggregate sandbox wall time: 3,600,000 ms per existing period (currently 300,000).
  This is one hour of accumulated execution time, **not** an authorization window.
- Keep the existing period, per-execution timeout, concurrency, queue, rate,
  identity, permissions and all retention settings unchanged.

These resource allowances avoid leaving the 50-run/200k-token bottleneck behind
after a currency increase. They are not formal student quotas. Do not install
any of these numbers in a generic starter, provider adapter or teaching default.

### Update contract after explicit confirmation

No executable grant/config has been written in this round. `update-policy`
requires a new policy version and preserves currency/period; it updates the
scoped policy but not the manifest's pinned cumulative ceiling. The legacy
`authorize-window` requires an expired timed authorization and grants a bounded
window; it cannot safely authorize this amount-only increase.

After confirmation, a minimal explicit amount-only grant operation is therefore
needed: lock and stop the matching instance, inspect old work, verify the expected
old cap/policy/deployment, use an authorization ID for idempotence, increment the
cap exactly once, and update scoped limits through `Ledger.update_policy`.
Journal the approved old/new values and resource limits. Preserve all rows and
unknown holds. DB policy and manifest are separate writes, so recovery must be
idempotent and fail closed; do not claim a cross-file atomic transaction or
silently edit only one side. Test this in isolation before applying. No new
prepare, stale-task replay or paid inference is needed for the update itself.

## 3. Formal teaching — requirements for Greg, NOT implemented

- Learners receive a fixed usage allowance refreshed daily or every configurable
  number of hours while course enrollment/access remains valid. Eligibility
  checks still run on submit, dispatch, external calls and publication. A new
  quota period never restores revoked/expired access.
- Learner period usage is distinct from cumulative class/course spending. A
  refresh opens a new accounting bucket; it does not erase historical usage,
  refund actual expenditure or reset the class/course total budget.
- Unknown reservations must remain liabilities across period boundaries until
  reconciliation. Confirm how an in-flight operation is attributed at rollover
  and ensure concurrency cannot oversubscribe learner or course budgets.
- Confirm quota units with Greg: tokens, monetary units, logical requests,
  sandbox resources, or a combination. One Ask/Run may make several model calls;
  a request quota and token/currency ledger are different concepts.
- Confirm period length, UTC/local timezone and fixed-vs-rolling boundaries,
  whether unused learner quota carries over (proposed default: no), course total
  duration, institutional ceiling, and behavior when a course budget is spent.
- Proposed responsibility split for discussion: course owner/Greg approves
  teaching entitlement and course funding; R1 supplies trusted enrollment,
  scope/version and access validity; controls owns reservation, settlement,
  period attribution and cumulative course limits; UI communicates availability
  and blockers without modifying grants. Admin configuration/audit ownership
  and API interfaces remain to be agreed.
- Current implementation has a shared `period_seconds` across scope limits and
  a deployment-wide cumulative model cap. This is **not** a completed independent
  learner-period + class/course-lifetime quota design. Existing `update_policy`
  rejects period changes without a separate ledger migration. Design the needed
  course-budget scope and interface before implementation; do not repurpose the
  local manifest or copy these developer limits into teaching configuration.

## 4. Verification and handoff summary

- Changed files: this plan, root README, team controls README.
- Completed: read-only ledger/config/code audit, task-to-attempt aggregation,
  local proposal and separate formal-course requirements.
- No runtime code, live policy, manifest, price, env, DB or credentials changed.
  Existing working-tree changes were preserved. No model calls or unknown-task
  retries; no service start/stop, prepare, commit, push or deployment.
- Tests: no runtime tests needed for documentation-only changes. Referenced file
  existence checks and `git diff --check` passed. End-of-audit DB SHA-256 matched
  the initial snapshot: `a1e9ceb837b58a8f379444c602aa1f658e697c86733beb2df032abc6a44b6fa2`;
  the persisted amount-only ceiling remained 148223 microunits.
  Paid replies, exact per-rejection
  dimension, proposed grant update/recovery and future course quotas are not
  verified or implemented by this round.
- Next dependency: user approval of an **incremental amount and companion local
  resource caps**. Formal teaching policy awaits Greg's decisions independently.
