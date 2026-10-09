# CC-R3 follow-up implementation summaries

Baseline: `a48b7b1`, `feature/shared-traffic-budget-controls`, original checkout.
Product decision: no learner-initiated Ask cancellation control. Existing backend
cancellation, fencing and evidence-backed recovery remain in place. No deployment,
branch merge, or paid model call is part of these rounds.

## Round A1 — worker outcome and execution boundaries (2026-10-09)

- Require a nonempty opaque result reference for completion. This closes empty
  completion, but actual stored-result validation still belongs to the HTTP/TTL
  integration, which is not installed here.
- Keep failed/cancelled work `unknown` when an external slot is active/unknown or
  an attempt remains reserved. Do not requeue it or refund uncertain liability.
- Preserve delivery of a usable answer when only provider usage is missing.
- Snapshot an independent execution deadline at dispatch. Heartbeats and later
  policy updates cannot extend it; late workers cannot publish or start another
  attempt. This is fencing, not remote process termination.
- Add explicit, repeatable operator schema upgrade. Legacy active jobs without a
  deadline fail closed as unknown; queued jobs get a deadline at dispatch.

Validation: SQLite full backend regression: **432 passed, 9 skipped** before
adding the separate PostgreSQL legacy-upgrade case. Targeted controls tests:
**46 passed, 2 skipped** on SQLite; **48 passed** on disposable PostgreSQL before
that additional case. The added PostgreSQL legacy-upgrade check then passed
separately (**1 passed**). Ruff lint/format and
mypy passed (108 source files). Tests use synthetic adapters/providers and
temporary databases, including timeout/replay, missing usage, empty result, late
response, heartbeat deadline, migration and cancellation. The PostgreSQL run
includes the two independent-process budget/concurrency races.

Remaining dependency: Step 1 verified identity and live grant recheck, followed by
owned TTL input/result storage and HTTP/worker integration. No end-to-end Ask claim.
