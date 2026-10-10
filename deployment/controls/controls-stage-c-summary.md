# Stage C: saved Ask, conversation restoration and controlled execution

## C0 — integration baseline (2026-10-10)

Goal: preserve the existing UI/R2 and bring the complete R1/R3 history together.
The actual starting tips were UI `ceef784`, R3 `1585b23`, main `e8725ec`.
The reported R3 `d7fa29b` is historical; no existing history was rewritten here.
Work is on `integration/saved-ask-controls`, created from the UI tip. Local main
is unchanged. Untracked deployment material and local SQLite files were backed up
outside Git before switching; none is staged. Locked live files stay in place.

Files: merged R3 controls/auth/config/tests/docs; resolved both router inclusions,
combined environment/privacy/architecture/validation documentation, retained UI
HTML and its auth/sidecar tests, added controls browser scripts and preserved both
API client exports. Retained pytest's pre-import temporary database isolation.

Result: complete R1 tip `266c23e` is an ancestor of R3; R2 `3a414d6` is an
ancestor of the UI base. No assumption about partial identity merges is needed.
Validation: Python compilation and staged whitespace check passed; signed HTTP
conversation, jobs-worker and grant regression tests: **36 passed, 0 failed,
0 skipped**. Full/backend/browser/PostgreSQL gates remain unverified at this step.
The retained UI still needs controlled API wiring; this merge is not Stage C
completion. Commit: this integration commit (recorded by the next step).

## Minimal implementation sequence and consistency decision

1. Add a content-free job/turn link and reuse R2 methods with an externally owned
   SQL transaction. Saved Ask requires dialogue and controls in the **same physical
   database**, explicitly configured, with both migrations installed. Existing
   R2 data is neither moved nor silently copied. Split-database deployments fail
   closed for saved Ask and need a separately designed outbox/recovery protocol.
2. Submit saved turns into existing admission, begin the R2 lease only at dispatch,
   check current grant/session/revision/expiry at every boundary, and atomically
   commit released dialogue + owned temporary result + job completion. No model
   call runs inside a database transaction. Unknown execution never requeues.
3. Connect existing optional-save UI and unsaved Stage B recovery. Persist opaque
   request pointers before POST; refresh/disconnect only query that request.
4. Exercise synthetic signed identities, model stubs, deletion/publication races,
   crash rollback, duplicate requests and PostgreSQL independent processes. Record
   local demo instructions and the exact remaining limits before updating UI.

R2 default saving, research consent separation, creation-based retention, external
deletion ledger, semester rules and governance vocabulary remain authoritative.
No cancellation button, teacher permission or code-execution job is in scope.

## C1 — shared transaction seam and owned turn link

Previous integration commit: `ea88b26`.
Goal: use the existing R2 transaction and turn contracts inside the coordinator.
Files: `conversations/repository.py`, `controls/{saved,data,ledger}.py`,
`tests/test_saved_transactions.py`. Added an additive, content-free
`control_conversations` table to explicit controls initialization/upgrade. R2
begin/complete accept an owned connection; normal R2 callers retain their existing
behavior. A completion in the outer transaction is idempotent. Shared transaction
rollback removes the assistant write and retains the pending learner turn.

Validation: **25 passed, 0 failed, 0 skipped** (transaction seam, existing
conversation lifecycle/repository and execution-data tests). Ruff targeted checks
and formatting passed after correcting an invocation's working-directory paths.
PostgreSQL, HTTP saved jobs and browser wiring remain unverified/not wired in this
step. Commit: this C1 commit (number recorded in C2).

## C2 — saved HTTP admission, worker and atomic publication

C1 commit: `31fd9ed`. Files: `controls/{saved,data,jobs_worker}.py`,
`conversations/{repository,router,bounds}.py`, `tests/test_saved_jobs.py`.
Both conversation edges now expose owned jobs/config/by-request routes. In
enforced mode the old turns route also enters admission, never synchronous paid
execution. Stable IDs bind original grant, conversation, revision and immutable
input. The worker loads completed history from R2, applies its context/model
bounds, and starts the existing turn lease only after queue dispatch.

Execution/external-call/publication/read checks enforce live original grant,
assignment version, owner, policy, deletion fence, expiry and revision/turn lease.
Released assistant message, encrypted result and job completion share one SQL
transaction. A crash rolls all three back; lease loss stays unknown and is not
model-replayed. Completed receipts survive a lost HTTP response. Dialogue delete
and maintenance erase linked execution content in their transaction. Expiry also
bounds temporary content and cleanup, without touching accounting liabilities.
Saved temporary results omit Glass Box/live analysis fields, matching R2's rule
that these summaries are not persisted or restored. Support recovery renders its
current institution frame; stored dialogue contains only neutral placeholders.

Validation: **47 passed, 0 failed, 0 skipped** (14 new saved integrations plus
existing worker/conversation HTTP and transaction tests). Initial failures from a
wall-clock test fixture and an incorrectly simulated crash were corrected; the
final run passed. Ruff passed; targeted mypy C1 passed. Full mypy, PostgreSQL,
browser wiring and manual visual verification are pending. Saving stays optional;
the strict Stage B operational content screen may reject a sensitive queued input
when distress routing is disabled instead of retaining it. No detector terms or
retention policy were changed. Commit: this C2 commit (recorded in C3).
