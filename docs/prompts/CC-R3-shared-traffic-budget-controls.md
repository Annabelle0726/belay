# CC-R3 - Shared traffic and budget controls

*Planning and implementation brief. Updated 2026-10-08 for
`feature/shared-traffic-budget-controls`, created directly from local
`main` at `83bd1a9`. Follow the numbered CC-B prompt structure.
This document proposes work; it does not claim that controls are implemented.*

Implementation progress is recorded in [controls-implementation.md](../controls-implementation.md),
with operator instructions in [controls-operations.md](../controls-operations.md).
The shared coordinator and execution hooks are implemented; production HTTP jobs
and real Step 1/2 conversation integration remain pending on this main-based branch.

Belay should remain usable when many students ask for help together.
One class must not occupy all available workers, adding servers must not
multiply allowances, and expensive work needs authorization before it starts.

---

## 1. Read first and verify the baseline

Read the actual files on this branch:

- `CONTRIBUTING.md`, `ARCHITECTURE.md`, `PRIVACY.md`, `VALIDATION.md`.
- The four existing `docs/prompts/CC-B*.md` files for structure and boundaries.
- `backend/app/main.py` and `backend/app/integrations/quad/router.py`:
  every endpoint that can start expensive work.
- `backend/app/agent/orchestrator.py`, `llm.py`, `telemetry.py`,
  `planner.py`, `self_eval.py`, `governance.py` and `injection_guard.py`:
  planning, generation, evaluation, safety checks, repairs and retries.
- `backend/app/store/db.py`, `models.py`, `repository.py` and `consent.py`:
  transaction support, learner storage and consent boundaries.
- `backend/app/analysis/measures.py`: existing usage/cost consumers.
- `backend/app/core/runner/` and `packs/datascience/grader.py`:
  direct and indirect code execution.
- Relevant backend and frontend request tests, deployment configuration,
  model SDK retry settings and provider usage reporting.

Do not list `auth.py`, `store/scoped.py` or `conversations/` as existing
main-branch files: they are dependencies in other branches, not this baseline.
Read their approved contracts when available; then update this inventory.

Produce a short inventory of chargeable paths, current measurements, missing
controls and integration dependencies before editing implementation code.
Telemetry after a call is not proof that spending was authorized before it.
Check whether SDK retries hide additional provider calls.

Portage may add gateway controls, but Belay must also protect standalone use.
Inspect actual Portage code and configuration before depending on an API.
Earlier inspected material included escalation ceilings, retry configuration
and course-key guidance; these do not establish a shared spending ledger or
fair class queue. Scheduling and task-budget design notes are not implementation.

## 2. Define what each control means

| Term | Plain meaning |
|---|---|
| Rate limit | How frequently new requests can arrive |
| Queue bound | How much accepted work can wait |
| Concurrency limit | How much work can run at the same time |
| Budget | How much a scope may spend in a defined period |
| Reservation | Allowance held before an expensive operation |
| Settlement | Replace the hold with actual or conservatively accounted usage |

All server instances must share one authoritative view of these controls.
An in-memory counter per server would multiply allowances when capacity grows.

**Recommended starting point, not an approved architecture:** use one
PostgreSQL coordinator for the first production implementation. Use atomic
transactions and scoped locking for reservations, queue claims and settlement.
Do not hold a database transaction open while calling a model.
SQLite can support local development; it does not prove multi-host behavior.
Avoid implementing both PostgreSQL and Redis coordinators in the first slice.

Apply learner, class, institution and deployment limits together using verified
Step 1 identity. A request is admissible only if every applicable parent and
child allowance permits it. Never accept a class or institution from an
untrusted request field as proof of membership.

Policies need explicit units, period/timezone, burst allowance, concurrency,
queue depth/bytes/wait, price version and currency. Validate configuration.
Represent unlimited and disabled explicitly; neither should be confused with zero.
Use exact accounting units for money rather than binary floating-point.

If the coordinator is unavailable, reject new spending in enforced mode.
Keep read-only course functions available where possible. Any development
bypass must be explicit and visibly labelled, never an automatic fallback.

Decisions to settle before production:
- Coordinator and operational owner.
- Actual learner/class/institution limits and budget periods.
- Equal class shares or approved scheduling weights.
- Exhausted budget: reject, or use a separately funded fallback.
- Accounting retention and access policy.

## 3. Add bounded admission and fair scheduling

Introduce one control boundary covering standalone and Quad entry points,
including indirect model and runner work. After Step 2 integration, saved and
unsaved turns must use the same resource controls.

Separate rate, queue, model concurrency and code-execution concurrency.
Bound queue depth, payload size, wait time and status polling.
A queue does not make accepted work free: limit outstanding financial liability
as well as the number of jobs, and check current funding again at dispatch.

Proposed initial fairness: rotate across eligible classes, serving each class's
jobs in arrival order. Eligibility includes all applicable limits. Shared
claiming must prevent multiple schedulers from multiplying a class's share.
A deployment-wide FIFO alone allows a busy class to dominate.

Use an authenticated, scoped operation ID. Reusing an ID with different input
must conflict; replay of a completed operation must not repeat work or charges.
Distinguish a logical request from each actual provider attempt.

For accepted asynchronous work, return an owned job ID and bounded status,
cancellation and result endpoints. Avoid leaving an HTTP thread occupied
merely while waiting. Recheck membership, grants, assignment/version and
conversation availability before execution and publication.

Define how workers reauthorize after the incoming credential expires.
Do not persist raw bearer tokens or treat an admission-time snapshot as
permanent authorization.

Queued input requires a clear storage, access and deletion policy.
Prefer references to permitted saved data. Unsaved requests need a bounded,
short-lived transfer mechanism, not an accidental permanent chat archive.
Ordinary course functionality must remain independent of research consent.

**Step 2 integration requirement:** its pending-turn lease and replay contract
must be reviewed after it is merged. Queue waiting must have a separate
lifetime from active execution, or pending execution must begin at dispatch
with revision/ownership checks. A valid turn must not expire just because
another class was using the workers.

## 4. Reserve budgets before spending

Keep operational accounting separate from saved dialogue and research events.
Budget enforcement must work when a student declines research participation
or disables saved dialogue.

A content-free ledger should record operation/attempt ID, verified scope,
budget period, policy/price version, reservation, reported usage, settlement
and unresolved outcome. Do not log prompts or student code to explain costs.

Before each actual model attempt, reserve a conservative bound covering input,
history and maximum billable output/reasoning where supported.
Account for planning, evaluation, refinement, repair, safety calls, retries and
fallbacks. Instrument or disable opaque SDK retries so no attempt is invisible.

Set supported provider output limits. Document where provider behavior or
billing prevents a perfect monetary upper bound; an estimate must not be
presented as a guaranteed invoice cap.

If Portage performs retries or fallback internally, require attributable
attempt usage or a bounded gateway contract. Avoid both double-counting
one call and missing calls hidden behind the gateway.

Settle each attempt once against authoritative usage where available.
Count billable failures too. Missing usage is unknown, not zero.
A timeout does not prove the provider stopped: retain uncertain liability
and reconcile it rather than issuing a free refund on lease expiry.

Record actual overruns, stop further spending and report the policy breach.
Do not clamp recorded usage to the reservation to conceal an overrun.
Queued holds and running holds need explicit budget-period rollover behavior.

Code execution needs separate run-count and CPU/wall-time/resource controls,
including grading and governance executions. A depleted allowance must not
cause required safety checks to be skipped. Return a safe unavailable result.

This milestone does not replace the runner's security boundary.
Do not claim B4's sandbox isolation without that implementation and validation.

## 5. Make failures and outcomes understandable

Use worker leases, heartbeats and fencing so stale workers cannot publish or
settle twice. Lease expiry alone does not establish that external work stopped.
Do not blindly retry an operation whose external outcome is unknown.

Queued cancellation releases unused reservations exactly once.
Running cancellation requests termination; active work and uncertain charges
remain accounted until termination or reconciliation is established.
Cancelling an HTTP coroutine may not stop a running thread or provider call.

Define recovery for crash, timeout, disconnect, duplicate delivery, coordinator
outage, grant revocation and deleted/expired conversations.
Do not promise exactly-once provider execution without a supporting provider
idempotency contract.

Learners should see waiting, running, retry-later, limit-reached, failed and
cancelled states with stable reason codes and retry timing where meaningful.
Do not expose another class's private usage or membership.

Provide an operator CLI or protected summary for queue wait/depth, active work,
rejections, reserved/consumed/unknown usage, retries and reconciliation health.
Student credentials must not authorize institution-wide inspection.
A new dashboard is optional; an inspectable summary is sufficient.

Demonstrate backend behavior with synthetic, clearly labelled limits:

| Demonstration | Expected evidence |
|---|---|
| Two API processes share a concurrency cap of 10 | Combined active work never exceeds 10 |
| Class A queues 50 jobs while B queues 2 | B receives service while A is still backlogged |
| 1,000 tokens remain and two requests each reserve 800 | Only one reservation succeeds |
| A model call retries after invalid JSON | Every billable attempt appears in accounting |
| The provider response is lost | Unknown usage remains held, not silently refunded |
| An authorized queued conversation is deleted | No dispatch/publication; holds are reconciled |

These are acceptance examples, not approved institutional allowances.

## 6. Build in small slices and prove the result

1. **Inventory and contracts.** Confirm the main baseline, chargeable paths,
   policy units, coordinator choice and Step 1/2 integration prerequisites.
2. **Shared ledger.** Add reservations, atomic parent/child checks, idempotent
   settlement, rollover and unknown-outcome reconciliation.
3. **Execution accounting.** Wrap every actual provider attempt and runner
   operation, including retries, fallbacks and safety work.
4. **Shared admission.** Add rate/concurrency controls, then bounded jobs,
   fair class scheduling and protected status/cancellation.
5. **Conversation and recovery integration.** Once approved prerequisites are
   on the base, connect replay, revisions, deletion and worker reauthorization.
6. **Observable validation.** Add learner messages, an operator summary,
   failure tests and a reproducible two-worker demonstration.

Test with temporary databases, deterministic clocks and provider/runner stubs.
Use independent processes/connections and real PostgreSQL transactions for
races; a mock or single-process SQLite test cannot prove shared enforcement.

Cover parent/child reservations, fairness, queue bounds, duplicate IDs,
duplicate settlement, all HTTP paths, retries, price/period changes, unknown
usage, overrun, cancellation, crashes, stale workers and coordinator outages.
After integration, include consent independence, scope isolation, revocation,
conversation deletion and payload cleanup. Check operator access boundaries.

Run the repository's required formatting, lint, typing and regression checks.
Report actual results and skips rather than copying prior branch pass counts.
Step 4's realistic class-sized load test remains a separate milestone;
Step 3 still needs tests proving its coordination rules.

**Expected outcome:** adding servers increases capacity without increasing
allowances. Classes receive bounded, fair service. Spending is checked before
execution, and failures do not silently erase usage or multiply charges.

For review, report the exact base, dependency status, migrations, policy units,
charged paths, fairness/recovery guarantees, limitations and demonstration.
Keep this planning change separate from later implementation commits.

No controls, tests, deployment, commit, push or feature-branch merge were
performed while authoring this document.
